"""Production configuration validation and safe HTTP-to-WSGI bridge."""
import io,logging,os,urllib.parse
from flask import Flask,request,Response
import server

def validate():
 if os.environ.get('HQ_ENV')!='production':return
 required=['DATABASE_URL','HQ_PUBLIC_URL','HQ_TOKEN_ENCRYPTION_KEY','SMTP_HOST','SMTP_FROM','HQ_OWNER_TOTP_SECRET']
 missing=[name for name in required if not os.environ.get(name)]
 if missing:raise RuntimeError('Missing production configuration: '+', '.join(missing))
 url=urllib.parse.urlsplit(os.environ['HQ_PUBLIC_URL'])
 if url.scheme!='https' or not url.hostname or url.path not in ['','/']:raise RuntimeError('HQ_PUBLIC_URL must be an HTTPS origin.')
 if os.environ.get('HQ_SECURE_COOKIE')!='1':raise RuntimeError('Production requires secure session cookies.')
 if not os.environ.get('PGSSLROOTCERT'):raise RuntimeError('Configure PGSSLROOTCERT for verified database TLS.')
 if (urllib.parse.urlsplit(os.environ['DATABASE_URL']).username or '').split('.')[0]!='digitalburj_app':raise RuntimeError('Use the restricted digitalburj_app database login at runtime.')
 import base64
 if len(base64.b32decode(os.environ['HQ_OWNER_TOTP_SECRET'].upper()+'='*((8-len(os.environ['HQ_OWNER_TOTP_SECRET'])%8)%8)))<20:raise RuntimeError('Owner authenticator secret must contain at least 20 random bytes.')
 if os.environ.get('SMTP_USER') and not os.environ.get('SMTP_PASSWORD'):raise RuntimeError('SMTP_PASSWORD is required for authenticated email.')
 from cryptography.fernet import Fernet
 Fernet(os.environ['HQ_TOKEN_ENCRYPTION_KEY'].encode())

class Bridge(server.Handler):
 def __init__(self):
  self.path=request.full_path.rstrip('?');self.headers=request.headers;self.client_address=(request.remote_addr or 'unknown',0)
  self.command=request.method;self.rfile=io.BytesIO(request.get_data());self.wfile=io.BytesIO();self.status=200;self.response_headers=[]
 def send_response(self,status,*args):
  self.status=status;self.response_headers=[];self.wfile.seek(0);self.wfile.truncate(0)
 def send_header(self,key,value):self.response_headers.append((key,value))
 def end_headers(self):pass

def create_app():
 os.environ.setdefault('HQ_ENV','production');validate();server.init();app=Flask(__name__,static_folder=None);app.config['MAX_CONTENT_LENGTH']=32768
 if os.environ.get('HQ_TRUST_PROXY')=='1':
  from werkzeug.middleware.proxy_fix import ProxyFix
  app.wsgi_app=ProxyFix(app.wsgi_app,x_for=1,x_proto=1)
 @app.before_request
 def host_check():
  configured=os.environ.get('HQ_PUBLIC_URL')
  # Railway's health probe sends its own Host header; /healthz returns no data, so allow only that pairing.
  if request.path=='/healthz' and request.host=='healthcheck.railway.app':return None
  if configured and request.host!=urllib.parse.urlsplit(configured).netloc:return Response('Invalid host',status=400)
 @app.route('/',defaults={'path':''},methods=['GET','POST'])
 @app.route('/<path:path>',methods=['GET','POST'])
 def dispatch(path):
  h=Bridge()
  try:h.do_POST() if request.method=='POST' else h.do_GET()
  except Exception as e:
   logging.error('HQ request failed: %s',type(e).__name__)
   return Response('{"error":"Service temporarily unavailable"}',status=503,mimetype='application/json')
  return Response(h.wfile.getvalue(),status=h.status,headers=h.response_headers)
 @app.after_request
 def security(response):
  response.headers['X-Content-Type-Options']='nosniff';response.headers['X-Frame-Options']='DENY';response.headers['Referrer-Policy']='same-origin';response.headers['Cache-Control']='no-store' if request.path.startswith('/api') else 'no-cache'
  if os.environ.get('HQ_ENV')=='production':response.headers['Strict-Transport-Security']='max-age=31536000; includeSubDomains'
  return response
 return app
