# -*- coding: utf-8 -*-

#  Copyright 2010 Adam Zapletal
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import os
import re
import base64
import htmlentitydefs
import mimetypes
import pygments
import sys
import utils

from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter


class Macro(object):
    """Base class for Macros. A Macro aims to analyse, process and eventually
    alter some provided HTML contents and to provide supplementary informations
    to the slide context.
    """
    def __init__(self, logger=sys.stdout, embed=False):
        self.logger = logger
        self.embed = embed

    def process(self, content, source=None):
        """Generic processor (does actually nothing)"""
        raise NotImplementedError(
            'Return the content and a list of classes to add to the slide')


class CodeHighlightingMacro(Macro):
    """This Macro performs syntax coloration in slide code blocks using
    Pygments.
    """
    code_blocks_re = re.compile(
        r'(<pre.+?>(<code>)?\s?!(\w+?)\n(.*?)(</code>)?</pre>)',
        re.UNICODE | re.MULTILINE | re.DOTALL
    )

    html_entity_re = re.compile('&(\w+?);')

    def descape(self, string, defs=htmlentitydefs.entitydefs):
        """Decodes html entities from a given string"""
        f = lambda m: defs[m.group(1)] if len(m.groups()) > 0 else m.group(0)
        return self.html_entity_re.sub(f, string)

    def process(self, content, source=None):
        classes = []
        code_blocks = self.code_blocks_re.findall(content)
        if not code_blocks:
            return content, classes

        for block, void1, lang, code, void2 in code_blocks:
            try:
                lexer = get_lexer_by_name(lang)
            except Exception:
                self.logger(u"Unknown pygment lexer \"%s\", skipping"
                            % lang, 'warning')
                return content, classes
            formatter = HtmlFormatter(linenos='inline', nobackground=True)
            pretty_code = pygments.highlight(self.descape(code), lexer,
                                             formatter)
            content = content.replace(block, pretty_code, 1)

        return content, [u'has_code']


class EmbedImagesMacro(Macro):
    """This Macro extracts images url and embed them using the base64
    algorithm.
    """
    def process(self, content, source=None):
        # TODO: Do the same with css?
        classes = []
        if not self.embed:
            return content, classes

        images = re.findall(r'<img\s.*?src="(.+?)"\s?.*?/?>', content,
                            re.DOTALL | re.UNICODE)
        if not images:
            return content, classes

        for image_url in images:
            if not image_url or image_url.startswith('data:'):
                continue

            if image_url.startswith('file://'):
                self.logger(u"%s: file:// image urls are not supported: "
                             "skipped" % source, 'warning')
                continue

            if (image_url.startswith('http://')
                or image_url.startswith('https://')):
                continue
            elif os.path.isabs(image_url):
                image_real_path = image_url
            else:
                image_real_path = os.path.join(os.path.dirname(source),
                                               image_url)

            if not os.path.exists(image_real_path):
                self.logger(u"%s: image file %s not found: skipped"
                            % (source, image_real_path), 'warning')
                continue

            mime_type, encoding = mimetypes.guess_type(image_real_path)

            if not mime_type:
                self.logger(u"%s: unknown image mime-type in %s: skipped"
                            % (source, image_real_path), 'warning')
                continue

            try:
                image_contents = open(image_real_path).read()
                encoded_image = base64.b64encode(image_contents)
            except IOError:
                self.logger(u"%s: unable to read image %s: skipping"
                            % (source, image_real_path), 'warning')
                continue
            except Exception:
                self.logger(u"%s: unable to base64-encode image %s: skipping"
                            % (source, image_real_path), 'warning')
                continue

            encoded_url = u"data:%s;base64,%s" % (mime_type, encoded_image)

            content = content.replace(image_url, encoded_url, 1)

            self.logger(u"Embedded image %s" % image_real_path, 'notice')

        return content, classes


class FixImagePathsMacro(Macro):
    """This Macro replaces html image paths with fully qualified absolute
    urls.
    """
    def process(self, content, source=None):
        classes = []

        if self.embed:
            return content, classes

        base_url = os.path.split(utils.get_abs_path_url(source))[0]
        fn = lambda p: r'<img src="%s" />' % os.path.join(base_url, p.group(1))

        sub_regex = r'<img.*?src="(?!http://)(.*?)".*/?>'

        content = re.sub(sub_regex, fn, content, re.UNICODE)

        return content, classes


class FxMacro(Macro):
    """This Macro processes fx directives, ie adds specific css classes
    named after what the parser found in them.
    """
    def process(self, content, source=None):
        classes = []

        fx_match = re.search(r'(<p>\.fx:\s?(.*?)</p>\n?)', content,
                             re.DOTALL | re.UNICODE)
        if fx_match:
            classes = fx_match.group(2).split(u' ')
            content = content.replace(fx_match.group(1), '', 1)

        return content, classes


class NotesMacro(Macro):
    """This Macro processes Notes."""
    def process(self, content, source=None):
        classes = []

        # A re.sub() call would require re.DOTALL but it's only been added in
        # python 2.7, implement it "at hand" to support python 2.6.
        new_content = ''
        last_index = 0
        for m in re.finditer(r'<p>\.notes:\s?(.*?)</p>', content, re.DOTALL):
          new_content += content[last_index:m.start()]
          new_content += '<p class="notes">%s</p>' % m.group(1)
          last_index = m.end()
        new_content += content[last_index:]

        if content != new_content:
            classes.append(u'has_notes')

        return new_content, classes
