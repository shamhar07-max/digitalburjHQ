import pathlib,sys,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import server,account_mail
server.init()
while True:
 with server.connection() as c:worked=account_mail.deliver(c)
 if not worked:time.sleep(5)
