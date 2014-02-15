#!/usr/bin/env python2

import cairo
import colorsys
import os
import yaml
import random
import wordcloud
import time
import re
import traceback
import htmlentitydefs
import sys
import praw
import numpy
import pyimgur
from os import path
from datetime import datetime
from PIL import Image
from HTMLParser import HTMLParser

def escapeHtml(what):
    return HTMLParser.unescape.__func__(HTMLParser, what)
    
def appendToFile(name, text):
    f = open(name, 'a+')
    f.write(text)
    f.close()

def cleanComment(comment):
    html = escapeHtml(comment.body_html)
    cp = CommentParser()
    cp.feed(html)
    return cp.text

class CommentParser(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self)
        self.text = ''
        self.aTags = 0
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.aTags += 1
    def handle_endtag(self, tag):
        if tag == 'a':
            self.aTags -= 1
    def handle_data(self, data):
        if self.aTags > 0 and data.startswith('http'):
            pass
        else:
            self.text += data
    def handle_entityref(self, name):
        self.text += htmlentitydefs.entitydefs[name].decode('utf-8', 'ignore')
    def handle_charref(self, name):
        if name[0] == 'x':
            self.text += unichr(int(name[1:], 16))
        else:
            self.text += unichr(int(name))

class Bot:
    def __init__(self):
        self.config = None
        self.d = path.dirname(__file__)
        self.images = []
        self.reddit = None
        self.respondedPath = path.join(self.d, 'responded-list.txt')
        self.respondedList = set()
        self.stopwords = set()
        self.doneDir = path.join(self.d, 'done')

    def load(self):
        self.loadConfig()
        self.loadImages()
        self.loadResponded()
        self.loadStopwords()
        self.createDoneDir()
        self.login()
        
    def log(self, text):
        print datetime.now().isoformat(), text

    def loadConfig(self):
        try:
            configDoc = open(path.join(self.d, 'config.yaml')).read()
        except IOError:
            self.log("'config.yaml' wasn't created.")
            exit(1)

        self.config = yaml.load(configDoc)
        self.log('Loaded config.')

    def loadImages(self):
        images = path.join(self.d, 'images')
        imagesPng = path.join(self.d, 'images-png')

        # Create the images-png dir.
        try:
            os.mkdir(imagesPng)
        except OSError:
            pass # Ignore if it exists.

        # Convert the images to PNGs if they don't exist.
        for f in os.listdir(images):
            image = {
                'original': path.join(images, f),
                'png': path.join(imagesPng, '.'.join(f.split('.')[:-1]) + '.png')
            }
            self.images.append(image)

            if not os.path.exists(image['png']):
                self.log('Making PDF variant for {0}'.format(image['original']))
                Image.open(image['original']).save(image['png'])
        
    def loadResponded(self):
        if not os.path.exists(self.respondedPath):
            return
        for line in open(self.respondedPath):
            line = line.strip()
            if len(line) > 0:
                self.respondedList.add(line)
        self.log('Loaded responded list with {0} IDs.'.format(
                len(self.respondedList)))
                
    def loadStopwords(self):
        stopwordsPath = path.join(self.d, 'stopwords.txt')
        for line in open(stopwordsPath):
            line = line.strip()
            if len(line) > 0:
                self.stopwords.add(line)
        self.log('Loaded stopwords list with {0} words.'.format(
                len(self.stopwords)))
                
    def createDoneDir(self):
        try:
            os.mkdir(self.doneDir)
        except:
            pass

    def login(self):
        self.reddit = praw.Reddit(self.config['userAgent'])
        self.reddit.login(self.config['username'], self.config['password'])
        self.log('Logged in as {0}.'.format(self.config['username']))
        
    def loop(self):
        while True:
            try:
                self.loopOnce()
            except:
                traceback.print_exc()
            time.sleep(self.config['pauseTime'])
            
    def loopOnce(self):
        for s in self.getGoodSubmissions():
            try:
                self.generate(s)
                time.sleep(self.config['pauseTime'])
            except reddit.errors.RateLimitExceeded as error:
                self.log('Sleeping for {0} seconds because of rate limiting.'
                        .format(error.sleep_time))
                time.sleep(error.sleep_time)
            except:
                self.log('Reddit problem:')
                traceback.print_exc()
                time.sleep(self.config['pauseTime'])
                continue
            
    def getGoodSubmissions(self):
        for s in self.reddit.get_subreddit('all').get_hot(limit=100):
            if s.id not in self.respondedList \
                    and s.num_comments >= self.config['minComments']:
                yield s

    def generate(self, s):
        self.addToRespondedList(s.id)
        
        text = self.getSubmissionText(s.id)
        words = self.getTopWords(text)
        dogeifiedWords = self.dogeifyWords(words)
        imagePath = self.makeDoge(dogeifiedWords, s.id)
        ui = self.uploadImage(imagePath)
        imagePath = self.addToImagePath(imagePath, ui.id)
        commentText = self.generateComment(ui.link)
        
        comment = s.add_comment(commentText)
        self.addToImagePath(imagePath, comment.id)
        self.log('Added the comment.')
        self.log('-' * 80)
        
    def addToRespondedList(self, sid):
        self.respondedList.add(sid)
        appendToFile(self.respondedPath, sid + '\n')

    def getSubmissionText(self, sid):
        s = self.reddit.get_submission(submission_id=sid, comment_limit=None)
        flatComments = praw.helpers.flatten_tree(s.comments)
        text = ''
        for comment in flatComments:
            if isinstance(comment, praw.objects.Comment):
                text += cleanComment(comment) + '\n'
        self.log('Got text for {0}.'.format(sid))
        return text

    def getTopWords(self, text):
        words = wordcloud.process_text(text, self.config['maxWords'],
                self.stopwords)
        return words

    def dogeifyWords(self, words):
        l = ['so', 'such', 'very', 'wow', 'much']
        ret = []
        for word, count in words:
            new = random.choice(l) + ' ' + word
            ret.append((new, count))
        return ret

    def makeDoge(self, words, sid):
        image = random.choice(self.images)
        
        img = Image.open(image['original'])
        width, height = img.size
        initialFontSize = int(height * self.config['initialFontSize'])
        elements = wordcloud.fit_words(words, width=width, height=height,
                font_path=self.config['fontPath'], prefer_horiz=1.0, 
                initial_font_size=initialFontSize)
        imagePath = '{0}-{1}.png'.format(datetime.now().isoformat(), sid)
        imagePath = path.join(self.doneDir, imagePath)                
        self.draw(image, elements, imagePath)
        return imagePath

    def draw(self, image, elements, imagePath):
        surface = cairo.ImageSurface.create_from_png(image['png'])
        ctx = cairo.Context(surface)
        ctx.select_font_face(self.config['fontName'], cairo.FONT_SLANT_NORMAL)

        for (word, count), font_size, position, _ in elements:
            ctx.set_font_size(font_size)

            hue = random.random()
            color = colorsys.hsv_to_rgb(hue, 0.9, 0.9)

            # The two libraries draw in different ways hence the modified Y.
            ctx.move_to(position[1], position[0] + font_size * 1.1)

            # Draw the text fill.
            ctx.text_path(word)
            ctx.set_source_rgb(*color)
            ctx.fill_preserve()

            # Draw the text stroke.
            ctx.set_source_rgb(1, 1, 1)
            ctx.set_source_rgb(0, 0, 0)
            ctx.set_line_width(font_size * self.config['fontStroke'])
            ctx.stroke()

        surface.write_to_png(imagePath)

    def uploadImage(self, imagePath):
        imgur = pyimgur.Imgur(self.config['imgurClientId'])
        ui = imgur.upload_image(imagePath)
        self.log('Uploaded image at {0}'.format(ui.link))
        return ui

    def generateComment(self, imageUrl):
        return self.config['commentFormat'].format(imageUrl=imageUrl)
        
    def addToImagePath(self, imagePath, text):
        newPath = imagePath[:-4] + '-' + text + '.png'
        os.rename(imagePath, newPath)
        return newPath

def main():
    bot = Bot()
    bot.load()
    bot.loop()

if __name__ == '__main__':
    main()

