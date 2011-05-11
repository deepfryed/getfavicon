import os,re,logging

from google.appengine.ext import webapp
from google.appengine.ext.webapp import util
from google.appengine.ext.webapp import template
from google.appengine.api import memcache
from google.appengine.api import urlfetch
from google.appengine.ext.db import stats

from urlparse import urlparse
from urlparse import urljoin
from datetime import *

from libs.counter import counter
from libs.beautifulsoup import BeautifulSoup

from globals import *
from models import *


class BaseHandler(webapp.RequestHandler):
  
  def htc(self,m):
    return chr(int(m.group(1),16))
  
  def urldecode(self,url):
    rex=re.compile('%([0-9a-hA-H][0-9a-hA-H])',re.M)
    return rex.sub(self.htc,url)
  
  def printTemplate(self,templateFile,templateVars):
    
    # Find the full system path
    templateFile = os.path.join(os.path.dirname(__file__), "templates/%s.html" % (templateFile))

    # Write it out
    self.response.out.write(template.render(templateFile,templateVars))
   
  def isDev(self):
    return os.environ.get("SERVER_SOFTWARE","").startswith("Development")
    
  def headlessDenial(self):
    self.error(404)
 
    
class deleteAll(BaseHandler):
  
  def get(self):
    
    if self.isDev():
      
      memcache.flush_all()
      
      allfavIconQuery = favIcon.all()
      favIcons = allfavIconQuery.fetch(500)
      db.delete(favIcons)


class cleanup(BaseHandler):

  def get(self):
    
    # Cleanup DS cache
    iconCacheCleanQuery = favIcon.gql("where dateCreated < :1",datetime.now()-timedelta(days=DS_CACHE_TIME))
    iconCacheCleanResults = iconCacheCleanQuery.fetch(500)
    db.delete(iconCacheCleanResults)
    
    # Update Counts
    counter.UpdateDSCounters()
   

class IndexPage(BaseHandler):
  
  def get(self):
    
    if HEADLESS:
      
      self.headlessDenial()
      
    else:
      
      # Last served icons query
      lastServedIconsQuery = favIcon.gql("where useDefault = False order by dateCreated desc")
      lastServedIcons = lastServedIconsQuery.fetch(22)
      
      # Retrieve counters
      favIconsServed = counter.GetCount("favIconsServed")
      favIconsServedDefault = counter.GetCount("favIconsServedDefault")
      iconFromCache = counter.GetCount("cacheMC") + counter.GetCount("cacheDS")
      iconNotFromCache = counter.GetCount("cacheNone")
      
      # Datastore stats
      if stats.GlobalStat.all().get():
        iconsCached = stats.GlobalStat.all().get().count
      else:
        iconsCached = None
    
      # Icon calculations
      favIconsServedM = round(float(favIconsServed) / 1000000,2)
      percentReal = round(float(favIconsServedDefault) / float(favIconsServed) * 100,2)
      percentCache = round(float(iconFromCache) / float(iconFromCache + iconNotFromCache) * 100,2)
    
      self.printTemplate("index",{
        "isHomepage":True,
        "favIconsServed":favIconsServedM,
        "percentReal":percentReal,
        "percentCache":percentCache,
        "iconsCached":iconsCached,
        "lastServedIcons":lastServedIcons
      })


class Decache(BaseHandler):
  
  def get(self):
    
    domain = self.request.get("domain")
    memcache.delete("icon-" + domain)
    
    deleteQuery = db.GqlQuery("SELECT __key__ FROM favIcon WHERE domain = :1", domain)
    db.delete(deleteQuery.fetch(100))
    

class TestPage(BaseHandler):

  def get(self):
    
    if HEADLESS:
      
      self.headlessDenial()
    
    else: 

      topSites = []
      topSitesFile = open("topsites.txt")
    
      for line in topSitesFile:
        topSites.append(line.replace("\n",""))
    
      self.printTemplate("test",{
        "isHomepage":False,
        "topSites":topSites,
        "isDev":self.isDev()
      })

    
class PrintFavicon(BaseHandler):
  
  def isValidIconResponse(self,iconResponse):
        
    iconLength = len(iconResponse.content)
    
    iconContentType = iconResponse.headers.get("Content-Type")
    if iconContentType:
      iconContentType = iconContentType.split(";")[0]
    
    invalidIconReason = []
    
    if not iconResponse.status_code == 200:
      invalidIconReason.append("Status code isn't 200")
      
    if iconContentType in ICON_MIMETYPE_BLACKLIST:
      invalidIconReason.append("Content-Type in ICON_MIMETYPE_BLACKLIST")
    
    if iconLength < MIN_ICON_LENGTH:
      invalidIconReason.append("Length below MIN_ICON_LENGTH")
    
    if iconLength > MAX_ICON_LENGTH:
      invalidIconReason.append("Length greater than MAX_ICON_LENGTH")
    
    if len(invalidIconReason) > 0:
      inf("Invalid icon because: %s" % invalidIconReason)
      return False
    else:
      return True
  
  
  def iconInMC(self):
    
    mcIcon = memcache.get("icon-" + self.targetDomain)
    
    if mcIcon:
      
      inf("Found icon MC cache")
      
      counter.ChangeCount("cacheMC",1)
      self.response.headers['X-Cache'] = "Hit from MC"
      
      if mcIcon == "DEFAULT":
        
        self.writeDefault(True)
        
        return True
        
      else:
        
        self.icon = mcIcon
        self.writeIcon()
        
        return True

    return False
    

  def iconInDS(self):
    
    iconCacheQuery = favIcon.gql("where domain = :1",self.targetDomain)
    iconCache = iconCacheQuery.fetch(1)
    
    if len(iconCache) > 0:
      
      inf("Found icon DS cache")
      
      counter.ChangeCount("cacheDS",1)
      self.response.headers['X-Cache'] = "Hit from DS"
      
      if iconCache[0].useDefault:
        
        self.writeDefault(True)
        return True
        
      else:
        
        self.icon = iconCache[0].icon
        
        self.cacheIcon(["MC"])
        self.writeIcon()
        
        return True
        
    return False

  
  def iconAtRoot(self):
    
    rootIconPath = self.targetDomain + "/favicon.ico"
    
    inf("iconAtRoot, trying %s" % rootIconPath)
    
    try:
      
      rootDomainFaviconResult = urlfetch.fetch(
        url = rootIconPath,
        follow_redirects = True,
      )
      
    except:
      
      inf("Failed to retrieve iconAtRoot")
      
      return False

    if self.isValidIconResponse(rootDomainFaviconResult):
          
      self.icon = rootDomainFaviconResult.content
      self.cacheIcon()
      self.writeIcon()
      
      return True
      
    else:
        
      return False
  
  
  def iconInPage(self):
  
    inf("iconInPage, trying %s" % self.targetPath)
    
    try:
      
      rootDomainPageResult = urlfetch.fetch(
        url = self.targetPath,
        follow_redirects = True,
      )
      
    except:
      
      inf("Failed to retrieve page to find icon")
      
      return False
    
    if rootDomainPageResult.status_code == 200:
      
      try:
        
        pageSoup = BeautifulSoup.BeautifulSoup(rootDomainPageResult.content)
        pageSoupIcon = pageSoup.find("link",rel=re.compile("^(shortcut|icon|shortcut icon)$",re.IGNORECASE))
        
      except:
        
        self.writeDefault()
        return False
               
      if pageSoupIcon:
                        
        pageIconHref = pageSoupIcon.get("href")

        if pageIconHref:
                    
          pageIconPath = urljoin(self.targetPath,pageIconHref)
          
        else:
          
          inf("No icon found in page")
          return False
        
        inf("Found unconfirmed iconInPage at %s" % pageIconPath)
        
        try:
          
          pagePathFaviconResult = urlfetch.fetch(pageIconPath)
          
        except:

          inf("Failed to retrieve icon to found in page")

          return False

        if self.isValidIconResponse(pagePathFaviconResult):
          
          self.icon = pagePathFaviconResult.content
          self.cacheIcon()
          self.writeIcon()
        
          return True
        
    return False
      
  
  def cacheIcon(self,cacheTo = ["DS","MC"]):
    
    inf("Caching to %s" % (cacheTo))
    
    # DS
    if "DS" in cacheTo:
      newFavicon = favIcon(
        domain = self.targetDomain,
        icon = self.icon,
        useDefault = False,
        referrer = self.request.headers.get("Referer")
      )
      newFavicon.put()
    
    # MC
    if "MC" in cacheTo:
      memcache.add("icon-" + self.targetDomain, self.icon, MC_CACHE_TIME)
  
  
  def writeHeaders(self):
    
    # MIME Type
    self.response.headers['Content-Type'] = "image/x-icon"
    
    # Set caching headers
    self.response.headers['Cache-Control'] = "public, max-age=2592000"
    self.response.headers['Expires'] = (datetime.now()+timedelta(days=30)).strftime("%a, %d %b %Y %H:%M:%S %z")


  def writeIcon(self):
    
    inf("Writing icon length %d bytes" % (len(self.icon)))
    
    self.writeHeaders()
    
    # Write out icon
    self.response.out.write(self.icon)
  
  
  def writeDefault(self, fromCache = False):
    
    inf("Writing default")
    
    self.writeHeaders()

    if not fromCache:
      
      newFavicon = favIcon(
        domain = self.targetDomain,
        icon = None,
        useDefault = True,
        referrer = self.request.headers.get("Referer")
      )
      newFavicon.put()

      memcache.add("icon-" + self.targetDomain, "DEFAULT", )

    counter.ChangeCount("favIconsServedDefault",1)
    
    if self.request.get("defaulticon"):
      
      if self.request.get("defaulticon") == "none":
        
        self.response.set_status(204)
      
      elif self.request.get("defaulticon") == "1pxgif":
        
        self.response.out.write(open("1px.gif").read())
        
      else:
        
        self.redirect(self.request.get("defaulticon"))
        
    else:
      
      self.response.out.write(open("default.gif").read())
  

  def get(self):
        
    counter.ChangeCount("favIconsServed",1)

    # Get page path
    self.targetPath = self.urldecode(self.request.path.lstrip("/"))
    
    inf("getFavicon for %s" % (self.targetPath))
    
    # Split path to get domain
    targetURL = urlparse(self.targetPath)
    self.targetDomain = "http://" + targetURL[1]
    
    inf("Domain is %s" % (self.targetDomain))
    
    # In MC?
    if not self.iconInMC():
      
      # In DS?
      if not self.iconInDS():
        
        counter.ChangeCount("cacheNone",1)
        
        # Icon at [domain]/favicon.ico?
        if not self.iconAtRoot():
          
          # Icon specified in page?
          if not self.iconInPage():
            
            self.writeDefault()
          


def main():
  
  logging.getLogger().setLevel(logging.DEBUG)
  
  application = webapp.WSGIApplication(
  [
    ('/', IndexPage),
    ('/decache/', Decache),
    ('/test/', TestPage),
    ('/_cleanup', cleanup),
    ('/_deleteall', deleteAll),
    ('/.*', PrintFavicon),
  ],
  debug=False
  )
  util.run_wsgi_app(application)


if __name__ == '__main__':
  main()
