#!/usr/bin/env python
import argparse
# import httplib
import logging
import pickle
import random
import re
import sys
import string
import signal
import time
import os
import shutil

from threading import Timer, RLock

import irc
import logger
import markov
from colortext import *

PARSER = argparse.ArgumentParser(description='A snarky IRC bot.')
PARSER.add_argument("--host", help="The server to connect to", default="irc.perl.org")
PARSER.add_argument("--port", type=int, help="The connection port", default=6667)
PARSER.add_argument("--nick", help="The bot's nickname", default="charrak")
PARSER.add_argument("--realname", help="The bot's real name", default="charrak the kobold")
PARSER.add_argument("--owners", help="The list of owner nicks", default="nrrd, nrrd_, mrdo, mrdo_")
PARSER.add_argument("--channels", help="The list of channels to join", default="#haplessvictims")
PARSER.add_argument("--save_period", help="How often (in seconds) to save databases", default=300)
PARSER.add_argument("--seendb", help="Path to seendb", default="./seendb.pkl")
PARSER.add_argument("--markovdb", help="Path to markovdb", default="./charrakdb")
PARSER.add_argument("--ignore", help="The optional list of nicks to ignore", default="")
PARSER.add_argument("--readonly", help="The bot will not learn from other users, only reply to them", dest='readonly', action='store_true')
PARSER.set_defaults(readonly=False)


class Bot(object):
    def __init__(self, args):
        # IRC settings
        self.irc = None
        self.HOST = args.host
        self.PORT = args.port
        self.NICK = args.nick
        self.REALNAME = args.realname
        self.OWNERS = [string.strip(owner) for owner in args.owners.split(",")]
        self.IGNORE = [string.strip(ignore) for ignore in args.ignore.split(",")]
        self.CHANNELINIT = [string.strip(channel) for channel in args.channels.split(",")]
        self.IDENT='pybot'
        self.READONLY = args.readonly

        # Caches of IRC status
        self.seen = {} # lists of who said what when

        # Markov chain settings
        self.p_reply = 0.1

        # Regular db saves
        self.SAVE_TIME = float(args.save_period)
        self.save_timer = None

        # Set up a lock for the seen db
        self.seendb_lock = RLock()
        self.SEENDB = args.seendb

        self.MARKOVDB = args.markovdb

        # signal handling
        signal.signal(signal.SIGINT, self.signalHandler)
        signal.signal(signal.SIGTERM, self.signalHandler)
        signal.signal(signal.SIGQUIT, self.signalHandler)

        # command registration
        self._commands = {
            '!seen': (self._cmd_seen, 'When I last saw someone.'),
            '!op': (self._cmd_op, 'Give someone ops.'),
            '!owners': (self._cmd_owners, 'Tell you who my owners are.'),
            '!ignore': (self._cmd_ignore, 'Begin ignoring someone.'),
            '!unignore': (self._cmd_unignore, 'Stop ignoring someone.'),
            '!help': (self._cmd_help, 'Get some help. No, seriously.'),
        }

    # Picks a random confused reply
    def dunno(self, msg):
        replies = ["I dunno, $who",
                   "I'm not following you."
                   "I'm not following you, $who."
                   "I don't understand.",
                   "You're confusing, $who."]

        which = random.randint(0, len(replies)-1)
        reply = re.sub("$who", msg["speaker"], replies[which])
        self.irc.privmsg(msg["speaking_to"], reply)

    # Join the IRC network
    def joinIRC(self):
        self.irc = irc.Irc(self.HOST, self.PORT, self.NICK, self.IDENT,
                           self.REALNAME)

        # Join the initial channels
        for chan in self.CHANNELINIT:
            self.irc.join(chan)
            if not self.irc.isop(self.NICK, chan):
                op_reqs = [
                    'Op me!', 'Yo, ops?',
                    'What does a kobold have to do to get ops around here?']
                which = random.randint(0, len(op_reqs)-1)
                self.irc.privmsg(chan, op_reqs[which])

    def initMarkovChain(self):
        # Open our Markov chain database
        self.mc = markov.MarkovChain(self.MARKOVDB)

    def loadSeenDB(self):
        with self.seendb_lock:
            try:
                with open(self.SEENDB, 'rb') as seendb:
                    self.seen = pickle.load(seendb)
            except IOError:
                logging.error(WARNING +
                              ("Unable to open seen db '%s' for reading" %
                               self.SEENDB))

    def saveSeenDB(self):
        with self.seendb_lock:
            try:
                with open(self.SEENDB, 'wb') as seendb:
                    pickle.dump(self.seen, seendb)
            except IOError:
                logging.error(ERROR +
                              ("Unable to open seed db '%s' for writing" %
                               self.SEENDB))

    def signalHandler(self, unused_signal, unused_frame):
        self.quit()

    def quit(self):
        if self.save_timer:
            self.save_timer.cancel()
        self.saveDatabases()
        self.irc = None
        sys.exit(0)

    @staticmethod
    def createBackup(source):
        if os.path.isfile(source):
            dst = source + ".bak"
            shutil.copyfile(source, dst)

    def saveDatabases(self):
        logging.info('Saving databases')
        self.createBackup(self.MARKOVDB)

        if self.READONLY:
            logging.info('Skipping markov db because we are read-only')
        else:
            self.mc.saveDatabase()

        self.createBackup(self.SEENDB)
        self.saveSeenDB()

    def handleSaveDatabasesTimer(self):
        self.saveDatabases()
        self.save_timer = Timer(self.SAVE_TIME, self.handleSaveDatabasesTimer)
        self.save_timer.start()

    @staticmethod
    def elapsedTime(ss):
        reply = ""
        startss = ss
        if ss > 31557600:
            years = ss // 31557600
            reply = reply + ("%g years " % years)
            ss = ss - years*31557600

        if ss > 2678400: # 31 days
            months = ss // 2678400
            reply = reply + ("%g months " % months)
            ss = ss - months*2678400

        if ss > 604800:
            weeks = ss // 604800
            reply = reply + ("%g weeks " % weeks)
            ss = ss - weeks*604800

        if ss > 86400:
            days = ss // 86400
            reply = reply + ("%g days " % days)
            ss = ss - days*86400

        if ss > 3600:
            hours = ss // 3600
            reply = reply + ("%g hours " % hours)
            ss = ss - hours*3600

        if ss > 60:
            minutes = ss // 60
            reply = reply + ("%g minutes " % minutes)
            ss = ss - minutes*60

        if ss != startss:
            reply = reply + "and "
        reply = reply + ("%.3f seconds ago" % ss)
        return reply

    def _cmd_seen(self, speaker, speaking_to, words):
        if len(words) != 2:
            return self._cmd_help(speaker, speaking_to, ['!help', 'seen'])

        nick = words[1]
        key = nick.lower()
        seen_msg = "I haven't seen " + nick + "."
        if self.seen.has_key(key):
            seen_msg = nick + ' was last seen in '
            seen_msg += self.seen[key][0] + ' '
            last_seen = self.seen[key][1] # in seconds since epoch
            since = self.elapsedTime(time.time() - last_seen)
            seen_msg += since
            message = string.strip(self.seen[key][2])
            seen_msg += ' saying "' + message + '"'

        self.irc.privmsg(speaking_to, seen_msg)
        return True

    def _cmd_op(self, speaker, speaking_to, words):
        if len(words) != 2:
            return self._cmd_help(speaker, speaking_to, ['!help', 'op'])

        # Am I an op?
        if not self.irc.isop(self.NICK):
            logging.info(YELLOW + 'not an op')
            self.irc.privmsg(speaking_to, "I'm going to need ops to do that")
            return False

        # Is the speaker an owner or an op?
        is_valid = (speaker in self.OWNERS) or self.irc.isop(speaker)

        if not is_valid:
            logging.info(YELLOW + ('%s is not an op or owner' % speaker))
            self.irc.privmsg(speaking_to,
                             'No can do. %s is not an op or owner' % speaker)
            return False

        self.irc.makeop(words[1])
        return True

    def _cmd_owners(self, speaker, speaking_to, words):
        if len(words) != 1:
            return self._cmd_help(speaker, speaking_to, ['!help', 'owners'])
        self.irc.privmsg(speaking_to, ('I would give up my bucket for %s' %
                                       ','.join(self.OWNERS)))

    def _cmd_ignore(self, speaker, speaking_to, words):
        if len(words) != 2:
            return self._cmd_help(speaker, speaking_to, ['!help', 'ignore'])

        # Is the speaker an owner or an op?
        is_valid = (speaker in self.OWNERS) or self.irc.isop(speaker)

        if not is_valid:
            logging.info(YELLOW + ('%s is not an op or owner' % speaker))
            self.irc.privmsg(speaking_to,
                             'No can do. %s is not an op or owner' % speaker)
            return False

        if words[1] not in self.IGNORE:
            self.IGNORE.append(words[1])
        return True

    def _cmd_unignore(self, speaker, speaking_to, words):
        if len(words) != 2:
            return self._cmd_help(speaker, speaking_to, ['!help', 'unignore'])

        # Is the speaker an owner or an op?
        is_valid = (speaker in self.OWNERS) or self.irc.isop(speaker)

        if not is_valid:
            logging.info(YELLOW + ('%s is not an op or owner' % speaker))
            self.irc.privmsg(speaking_to,
                             'No can do. %s is not an op or owner' % speaker)
            return False

        if words[1] in self.IGNORE:
            self.IGNORE.remove(words[1])
        return True

    def _cmd_help(self, speaker, speaking_to, words):
        if len(words) == 1:
            self.irc.privmsg(speaking_to,
                             ('I know the following commands: %s. '
                              'Try \'!help <command>\' to find out more.' %
                              ','.join(list(self._commands))))
            return True
        elif words[1] in self._commands:
            self.irc.privmsg(speaking_to, self._commands[words[1]][1])
            return True

        return False

    def handleCommands(self, msg):
        # parse the message
        words = msg["text"].split()

        # Handle messages such as "charrak?"
        if len(words) < 1:
            return False

        if words[0] in self._commands:
            cmd = self._commands[words[0]][0]
            return cmd(msg['speaker'], msg['speaking_to'], words)

        return False

    @staticmethod
    def logChannel(speaker, msg):
        logging.debug(CYAN + speaker + PLAIN + " : " + BLUE + msg)

    def possiblyReply(self, msg):
        PUNCTUATION = ",./?><;:[]{}\'\"!@#$%^&*()_-+="
        words = string.strip(msg["text"], PUNCTUATION).split()

        leading_words = ""
        seed = None

        # If we have enough words and the random chance is enough, reply based on the message.
        if len(words) >= 2 and random.random() <= msg["p_reply"]:
            logging.info(GREEN + "Trying to reply to '" + str(words) + "'")
            # Use a random bigram of the input message as a seed for the Markov chain
            max_index = min(6, len(words)-1)
            index = random.randint(1, max_index)
            seed = (words[index-1], words[index])
            leading_words = string.join(words[0:index+1])

        # If not, and we weren't referenced explicitly in the message, return early.
        # TODO: fix issue where this doesn't match if NICK contains one of PUNCTUATION.
        if not seed and (self.NICK.lower() not in [string.strip(word, PUNCTUATION).lower() for word in words]):
            return

        # generate a response
        response = string.strip(self.mc.respond(seed))
        if len(leading_words) > 0:
            leading_words = leading_words + " "
        reply = leading_words + response
        #print string.join(seed) + " :: " + reply
        if len(response) == 0:
            self.logChannel(self.NICK, "EMPTY_REPLY")
        else:
            self.irc.privmsg(msg["speaking_to"], reply)
            self.logChannel(self.NICK, reply)

    # @staticmethod
    # def makeTinyUrl(url):
    #     # make a request to tinyurl.com to translate a url.
    #     # their API is of the format:
    #     # 'http://tinyurl.com/api-create.php?url=' + url
    #     conn = httplib.HTTPConnection("tinyurl.com")
    #     conn.request("GET", "api-create.php?url=" + url)
    #     r1 = conn.getresponse()
    #     if r1.status == 200:
    #         irc.send('PRIVMSG '+OWNER+' :' + r1.read() + '\r\n')
    #     else:
    #         msg = 'Tinyurl problem: status=' + str(r1.status)
    #         self.irc.privmsg(OWNER, msg)
    #     return


    def parsePublicMessage(self, msg):
        q = re.search('.*(http://\S*)', msg["text"])
        if q is not None:
            #self.makeTinyUrl( str(q.groups(0)[0]) )
            return

        # add the spoken phrase to the log
        self.logChannel(msg["speaker"], msg["text"])

        # If a user has issued a command, don't do anything else.
        if self.handleCommands(msg):
            return

        self.possiblyReply(msg)

        # add the phrase to the markov database if we're NOT in
        # readonly mode
        if not self.READONLY:
            self.mc.addLine(msg["text"])

    def parsePrivateOwnerMessage(self, msg):
        # The owner can issue commands to the bot, via strictly
        # constructed private messages
        words = msg["text"].split()

        logging.info("Received private message: '" +
                     string.strip(msg["text"]) + "'")

        # simple testing
        if len(words) == 1 and words[0] == 'ping':
            self.logChannel(msg["speaker"], GREEN + 'pong')
            self.irc.privmsg(msg["speaker"], 'pong')
            return

        # set internal variables
        elif len(words) == 3 and words[0] == "set":
            # set reply probability
            if words[1] == "p_reply":
                self.logChannel(msg["speaker"],
                                GREEN + "SET P_REPLY " + words[2])
                self.p_reply = float(words[2])
                self.irc.privmsg(msg["speaker"], str(self.p_reply))
            else:
                self.dunno(msg)
            return

        elif len(words) == 2 and words[0] == "get":
            # set reply probability
            if words[1] == "p_reply":
                self.logChannel(msg["speaker"],
                                GREEN + "GET P_REPLY " + str(self.p_reply))
                self.irc.privmsg(msg["speaker"], str(self.p_reply))
                return

        # leave a channel
        elif len(words) == 2 and (words[0] == 'leave' or words[0] == 'part'):
            self.logChannel(msg["speaker"], PURPLE + "PART " + words[1])
            self.irc.part(words[1])
            return

        # join a channel
        elif len(words) == 2 and words[0] == 'join':
            channel = str(words[1])
            if channel[0] != '#':
                channel = '#' + channel

            self.logChannel(msg["speaker"], PURPLE + "JOIN " + channel)
            self.irc.send('JOIN ' + channel + '\r\n')
            return

        # quit
        elif len(words) == 1 and (words[0] == 'quit' or words[0] == 'exit'):
            self.logChannel(msg["speaker"], RED + "QUIT")
            self.quit()

        # if we've hit no special commands, parse this message like it was public
        self.parsePublicMessage(msg)

    @staticmethod
    def preprocessText(text):
        # remove all color codes
        text = re.sub('\x03(?:\d{1,2}(?:,\d{1,2})?)?', '', text)
        return text

    def determineWhoIsBeingAddressed(self, msg):
        msg["addressing"] = ""
        words = msg["text"].split()
        if len(words) == 0:
            return

        # strip off direct addressing (i.e. "jeff: go jump in a lake")
        first_word = words[0].rstrip(":,!?")

        # if the person is speaking to the channel
        if msg["speaking_to"][0] == "#":
            # see if we're being spoken to.
            if first_word == self.NICK:
                msg["p_reply"] = 1.0
            #..search the channel for nicks matchig this word
            elif first_word in self.irc.who[msg["speaking_to"]]:
                #..and snip them out if they're found
                msg["addressing"] = first_word
                newline = string.join(words[1:], " ")
                msg["text"] = newline
                if first_word == self.NICK:
                    msg["p_reply"] = 1.0
        else:
            # ..otherwise we're being directly addressed
            msg["p_reply"] = 1.0

    # private message from user
    # :nrrd!~jeff@bacon2.burri.to PRIVMSG gravy :foo
    # public channel message
    # :nrrd!~jeff@bacon2.burri.to PRIVMSG #test333 :foo
    # TODO: take 'words' instead to simplify parsing.
    def parsePrivMessage(self, line):
        # ignore any line with a url in it
        m = re.search('^:(\w*)!.(\w*)@(\S*)\s(\S*)\s(\S*) :(.*)', line)
        if m is None:
            return

        text = m.group(6)
        text = self.preprocessText(text)

        msg = {
            "speaker"       : m.group(1) ,                # the nick of who's speaking
            "speaker_email" : m.group(2)+'@'+m.group(3),  # foo@bar.com
            "privmsg"       : m.group(4),                 # should be PRIVMSG
            "speaking_to"   : m.group(5),                 # could be self.NICK or a channel
            "text"          : text,                       # what's said
            "p_reply"       : self.p_reply                # probably of responding
        }

        if msg["privmsg"] != 'PRIVMSG':
            return

        if msg["speaking_to"][0] == "#":
            nick = msg["speaker"].lower()
            # Lock here to avoid writing to the seen database while pickling it.
            with self.seendb_lock:
                self.seen[nick] = [msg["speaking_to"], time.time(),
                                   string.strip(msg["text"])]

        if msg["speaker"] in self.IGNORE:
            return

        if msg["speaking_to"] == self.NICK and msg["speaker"] in self.OWNERS:
            self.parsePrivateOwnerMessage(msg)
        elif msg["speaking_to"] != self.NICK:
            self.parsePublicMessage(msg)

    # information about MODE changes (ops, etc.) in channels
    def parseModeMessage(self, words):
        # right now, we only care about ops
        if len(words) < 5:
            return
        channel = words[2]
        action = words[3]
        on_who = words[4]

        if action == "+o":
            self.irc.addop(channel, on_who)
            return

        if action == "-o":
            self.irc.rmop(channel, on_who)
            return

    # update who list when users part or join.
    def handlePartJoin(self, words):
        m = re.search('^:(\w*)!', words[0])
        if m is None:
            return

        user = m.group(1)
        channel = words[2]

        if words[1] == 'PART':
            self.irc.rmwho(channel, user)
        elif words[1] == 'JOIN':
            # strip the leading ':'
            self.irc.addwho(channel[1:], user)

    def main(self):
        logger.initialize("./")
        self.initMarkovChain()
        self.loadSeenDB()
        self.joinIRC()

        self.save_timer = Timer(self.SAVE_TIME, self.handleSaveDatabasesTimer)
        self.save_timer.start()

        # Loop forever, parsing input text
        while True:
            try:
                recv = self.irc.readlines()
            except irc.ConnectionClosedException:
                logging.warning(WARNING + "Connection closed: Trying to reconnect in 5 seconds...")
                time.sleep(5)
                self.joinIRC()
                continue

            for line in recv:
                logging.debug(line)
                # strip whitespace and split into words
                words = string.rstrip(line)
                words = string.split(words)

                if words[0]=="PING":
                    self.irc.pong(words[1])
                elif words[1] == 'PRIVMSG':
                    self.parsePrivMessage(line)
                elif words[1] == "MODE":
                    self.parseModeMessage(words)
                elif words[1] == 'PART' or words[1] == 'JOIN':
                    self.handlePartJoin(words)

#####

if __name__ == "__main__":
    bot = Bot(PARSER.parse_args())
    bot.main()
