import os
import sys
import ssl
import time

from datetime						import datetime
from multiprocessing				import Process

from threading                      import Thread
from socketserver                   import ThreadingMixIn
from http.server                    import HTTPServer

from src.log						import LOG, ACCESS
from src.server                     import SERVER
from src.define                     import *

from src.system.disk                import DISK
from src.system.backup				import BACKUP

from src.system.db.mysql            import MYSQL
from src.system.db.db_user          import DB_USER
from src.system.db.db_hosting       import DB_HOSTING



class ThreadBaseServer(ThreadingMixIn, HTTPServer): ...

def process_backup():
	print("BACKUP PID: ", os.getpid())
	datetime_run			= datetime.now()
	while True:
		try:
			if (datetime.now() - datetime_run).days	> 1:
				print("backup")
				# thực hiện đồng bộ log
				LOG.backup()
				ACCESS.backup()
				# thực hiện đồng bộ dữ liệu toàn hệ thống
				BACKUP.all()
				# cập nhật lại thông tin 
				datetime_run		= datetime.now()
			# wait time
			time.sleep(60)
		except Exception as e:
			_, _, exc_tb = sys.exc_info()
			fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
			LOG.append(str(e) + "\tFile: " + fname + "\tLine: " + str(exc_tb.tb_lineno))
			return

try:
	print(datetime.now())
	print("==================== SERVER RUN ====================")
	print("USER: ",	os.geteuid())
	print("PID: ", os.getpid())

	# thực hiện chạy tiến trình backup
	p_backup		= Process(target=process_backup)
	p_backup.start()


	# thực hiện liên kết tới CSDL MYSQL
	MYSQL.MS_connection	= MYSQL.connection(host="localhost", user="ubuntu", password="Admin1234@")
	# tạo luồng để duy trì kết nối
	# load thông tin customer
	db_user			= DB_USER()
	db_hosting		= DB_HOSTING()

	customers		= db_user.get()
	# duyệt thông tin người dùng
	for customer in customers:
		# lấy danh sách hosting của người dùng
		hosting		= db_hosting.find(username=customer['USERNAME'])
		# duyệt qua danh sách hosting 
		for host in hosting:
			vhd_path	= os.path.join(PATH_VHD_USERS, f"{host['HOSTING']}_vhd.img")
			# kiểm tra đường dẫn valid
			if os.path.isfile(vhd_path):
				# thực hiện mount đối tượng
				DISK.mount_vhd_to_home_user(vhd_path, host['HOME'])

	thread_hold			= Thread(target=MYSQL.holding)
	thread_hold.start()
	## khợi tạo server chạy với port 2440
	server				= ThreadBaseServer(("172.16.1.244", 2440), SERVER)

	sslcontext			= ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
	sslcontext.load_cert_chain(
		keyfile			= PATH_CERT_SUBDOMAIN_KEY,
		certfile		= PATH_CERT_SUBDOMAIN_FILE
	)
	server.socket		= sslcontext.wrap_socket(server.socket, server_side=True)
	server.serve_forever()
	
	p_backup.kill()
except Exception as e:
	_, _, exc_tb = sys.exc_info()
	fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
	LOG.append(str(e) + "\tFile: " + fname + "\tLine: " + str(exc_tb.tb_lineno))
	# đóng kết nối tới csdl
	MYSQL.MS_connection.close()
	sys.exit(0)