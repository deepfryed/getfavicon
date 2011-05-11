from google.appengine.ext import db

class CounterShard(db.Model):
  name = db.StringProperty(required=True)
  count = db.IntegerProperty(default=0)
  
class favIcon(db.Model):
  domain = db.StringProperty(required=True)
  icon = db.BlobProperty(default=None)
  useDefault = db.BooleanProperty(default=True)
  dateCreated = db.DateTimeProperty(auto_now_add=True)
  referrer = db.StringProperty()