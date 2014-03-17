import sys
import os
import re
import codecs
from logging import CRITICAL, DEBUG, INFO 
from collections import OrderedDict
from plasTeX.Renderers import XHTML
from plasTeX.TeX import TeX
from plasTeX.Renderers.PageTemplate import Renderer as _Renderer
from plasTeX.Config import config as plasTeXconfig
from xml.sax.saxutils import escape, unescape
from abox import AnswerBox, split_args_with_quoted_strings

class MyRenderer(XHTML.Renderer):
    """
    PlasTeX class for rendering the latex document into XHTML + edX tags
    """
    def __init__(self, imdir='', imurl='', extra_filters=None):
        '''
        imdir = directory where images should be stored
        imurl = url base for web base location of images
        '''
        XHTML.Renderer.__init__(self)
        self.imdir = imdir
        self.imurl = imurl
        self.imfnset = []

        # setup filters
        self.filters = OrderedDict()
        for ffm in self.filter_fix_math_match:
            self.filters[ffm] = self.filter_fix_math
        for ffm in self.filter_fix_displaymath_match:
            self.filters[ffm] = self.filter_fix_displaymath
        self.filters[self.filter_fix_abox_match] = self.filter_fix_abox
        self.filters[self.filter_fix_image_match] = self.filter_fix_image
        self.filters[self.filter_fix_edxxml_match] = self.filter_fix_edxxml

        if extra_filters is not None:
            self.filters.update(extra_filters)

    filter_fix_edxxml_match = '(?s)<edxxml>\\\\edXxml{(.*?)}</edxxml>'

    @staticmethod
    def filter_fix_edxxml(m):
        xmlstr = m.group(1)
        xmlstr = xmlstr.replace('\\$','$')	# dollar sign must be escaped in plasTeX, but shouldn't be in XML
        # return xmlstr
        return "<edxxml>%s</edxxml>" % xmlstr

    @staticmethod
    def fix_math_common(m):
        x = m.group(1).strip()
        x = x.replace(u'\u2019',"'")
        x = x.decode('ascii','ignore')
        x = x.replace('\\ensuremath','')
        x = x.replace('{^\\circ','{}^\\circ')	# workaround plasTeX bug
        x = x.replace('\n','')
        x = escape(x)
        return x

    filter_fix_math_match  = ['(?s)<math>\$(.*?)\$</math>',
                              '(?s)<math>\\\\ensuremath{(.*?)}</math>']

    @classmethod
    def filter_fix_math(cls, m):
        x = cls.fix_math_common(m)
        if len(x)==0 or x=="\displaystyle":
            return "&nbsp;"
        return '[mathjaxinline]%s[/mathjaxinline]' % x
        
    filter_fix_displaymath_match = [r'(?s)<math>\\begin{equation}(.*?)\\end{equation}</math>',
                                    r'(?s)<displaymath>\\begin{edXmath}(.*?)\\end{edXmath}</displaymath>',
                                    r'(?s)<math>\\\[(.*?)\\\]</math>',
                                    ]

    @classmethod
    def filter_fix_displaymath(cls, m):
        x = cls.fix_math_common(m)
        if len(x)==0 or x=="\displaystyle":
            return "&nbsp;"
        return '[mathjax]%s[/mathjax]' % x

    filter_fix_image_match = '<includegraphics style="(.*?)">(.*?)</includegraphics>'

    def filter_fix_image(self, m):
        print "[do_image] m=%s" % repr(m.groups())
        style = m.group(1)
        sm = re.search('width=([0-9\.]+)(.*)',style)
        if sm:
            widtype = sm.group(2)
            width = float(sm.group(1))
            if 'in' in widtype:
                width = width * 110
            elif 'cm' in widtype:
                width = width * 110 / 2.54
            if 'extwidth' in widtype:
                width = width * 110 * 6
            width = int(width)
            if width==0:
                width = 400
        else:
            width = 400

        def make_image_html(fn,k):
            self.imfnset.append(fn+k)
            # if file doesn't exist in edX web directory, copy it there
            fnbase = os.path.basename(fn)+k
            wwwfn = '%s/%s' % (self.imdir,fnbase)
            #if not os.path.exists('/home/WWW' + wwwfn):
            if 1:
                cmd = 'cp %s %s' % (fn+k,wwwfn)
                os.system(cmd)
                print cmd
                os.system('chmod og+r %s' % wwwfn)
            return '<img src="/static/%s/%s" width="%d" />' % (self.imurl,fnbase,width)

        fnset = [m.group(2)]
        fnsuftab = ['','.png','.pdf','.png','.jpg']
        for k in fnsuftab:
            for fn in fnset:
                if os.path.exists(fn+k):
                    if k=='.pdf':		# convert pdf to png
                        dim = width if width>400 else 400
                        # see how many pages it is
                        try:
                            npages = int(os.popen('pdfinfo %s.pdf | grep Pages:' % fn).read()[6:].strip())
                        except Exception, err:
                            # print "npages error %s" % err
                            npages = 1
                        nfound = 0
                        if npages>1:	# handle multi-page PDFs
                            fnset = ['%s-%d' % (fn,x) for x in range(npages)]
                            nfound = sum([ 1 if os.path.exists(x+'.png') else 0 for x in fnset])
                            print "--> %d page PDF, fnset=%s (nfound=%d)" % (npages, fnset, nfound)
                        if not nfound==npages:
                            os.system('convert -density 800 {fn}.pdf -scale {dim}x{dim} {fn}.png'.format(fn=fn,dim=dim))
                        if npages>1:	# handle multi-page PDFs
                            fnset = ['%s-%d' % (fn,x) for x in range(npages)]
                            print "--> %d page PDF, fnset=%s" % (npages, fnset)
                        else:
                            fnset = [fn]
                        imghtml = ''
                        for fn2 in fnset:
                            imghtml += make_image_html(fn2,'.png')
                        return imghtml
                    else:
                        return make_image_html(fn,k)
                
        fn = fnset[0]
        print 'Cannot find image file %s' % fn
        return '<img src="NOTFOUND-%s" />' % fn

    filter_fix_abox_match = r'(?s)<abox>(.*?)</abox>'

    @staticmethod
    def filter_fix_abox(m):
        return AnswerBox(m.group(1)).xmlstr

    @staticmethod
    def fix_unicode(stxt):
        ucfixset = { u'\u201d': '"',
                     u'\u2014': '-',
                     u'\u2013': '-',
                     u'\u2019': "'",
                     }

        for pre, post in ucfixset.iteritems():
            try:
                stxt = stxt.replace(pre, post)
            except Exception, err:
                print "Error in rendering (fix unicode): ",err
        return stxt

    def processFileContent(self, document, stxt):
        stxt = XHTML.Renderer.processFileContent(self, document, stxt)
        stxt = self.fix_unicode(stxt)

        for fmatch, filfun in self.filters.iteritems():
            try:
                stxt = re.sub(fmatch, filfun, stxt)
            except Exception, err:
                print "Error in rendering %s: %s" % (filfun, str(err))
                raise

        stxt = stxt.replace('<p>','<p>\n')
        stxt = stxt.replace('<li>','\n<li>')
        stxt = stxt.replace('&nbsp;','&#160;')

        stxt = stxt[stxt.index('<body>')+6:stxt.index('</body>')]

        XML_HEADER = '<document>'
        XML_TRAILER = '</document>'

        self.xhtml = XML_HEADER + stxt + XML_TRAILER
        return self.xhtml

    def cleanup(self, document, files, postProcess=None):
        res = _Renderer.cleanup(self, document, files, postProcess=postProcess)
        return res


class plastex2xhtml(object):
    '''
    Use plastex to convert .tex file to .xhtml, with special edX macros.

    This procecss requires the "render" directory, with its .zpts files, as well
    as the edXpsl.py file, with its plastex python macros.

    '''

    def __init__(self,
                 fn,
                 imdir="static/images",
                 imurl="",
                 fp=None,
                 extra_filters=None,
                 latex_string=None,
                 add_wrap=False,
                 verbose=False):
        '''
        fn            = tex filename (should end in .tex)
        imdir         = directory where images are to be stored
        imurl         = web root for images
        fp            = file object (optional) - used instead of open(fn), if provided
        extra_filters = dict with key=regular exp, value=function for search-replace, for
                        post-processing of XHTML output
        latex_string  = latex string (overrides fp and fn)
        add_wrap      = if True, then assume latex is partial, and add preamble and postfix
        verbose       = if True, then do verbose logging
        '''

        if fn.endswith('.tex'):
            ofn = fn[:-4]+'.xhtml'
        else:
            ofn = fn + ".xhtml"

        self.input_fn = fn
        self.output_fn = ofn
        self.fp = fp
        self.latex_string = latex_string
        self.add_wrap = add_wrap
        self.verbose = verbose
        self.renderer = MyRenderer(imdir, imurl, extra_filters)

        # Instantiate a TeX processor and parse the input text
        tex = TeX()
        tex.ownerDocument.config['files']['split-level'] = -100
        tex.ownerDocument.config['files']['filename'] = self.output_fn
        tex.ownerDocument.config['general']['theme'] = 'plain'

        plasTeXconfig.add_section('logging')
        plasTeXconfig['logging'][''] = CRITICAL

        self.tex = tex
        if not self.verbose:
            tex.disableLogging()

    def convert(self):
        self.generate_xhtml()	# do conversion

    def generate_xhtml(self):

        if self.verbose:
            print "============================================================================="
            print "Converting latex to XHTML using PlasTeX with custom edX macros"
            print "Source file: %s" % self.input_fn
            print "============================================================================="
    
        # set the zpts templates path
        mydir = os.path.dirname(__file__)
        zptspath = os.path.abspath(mydir + '/render')
        os.environ['XHTMLTEMPLATES'] = zptspath

        # print os.environ['XHTMLTEMPLATES']

        # add our python plastex package directory to python path
        plastexpydir = os.path.abspath(mydir + '/plastexpy')
        sys.path.append(plastexpydir)

        # get the input latex file
        if self.latex_string is None:
            if self.fp is None:
                self.fp = codecs.open(self.input_fn)
            self.latex_string = self.fp.read()
            self.latex_string = self.latex_string.replace('\r','\n') # convert from mac format EOL
        
        # add preamble and postfix wrap?
        if self.add_wrap:
            PRE = """\\documentclass[12pt]{article}\n\\usepackage{edXpsl}\n\n\\begin{document}\n\n"""
            POST = "\n\n\\end{document}"
            self.latex_string = PRE + self.latex_string + POST
 
        self.tex.input(self.latex_string)
        document = self.tex.parse()
        
        self.renderer.render(document)

        print "XHTML generated (%s): %d lines" % (self.output_fn, len(self.renderer.xhtml.split('\n')))
        return self.renderer.xhtml

    @property
    def xhtml(self):
        return self.renderer.xhtml
    