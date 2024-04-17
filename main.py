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
from src.cert						import CERT
from src.server                     import SERVER
from src.define                     import *

from src.nginx						import NGINX
from src.ftp.ftp					import FTP
from src.php.php_configure			import PHP_CONFIGURE

from src.system.disk                import DISK
from src.system.backup				import BACKUP

from src.system.db.mysql            import MYSQL
from src.system.db.db_user          import DB_USER
from src.system.db.db_hosting       import DB_HOSTING
from src.system.db.db_database		import DB_DATABASE
from src.system.db.db_feature		import DB_FEATURE
from src.system.db.db_domain		import DB_DOMAIN

from src.system.db.db_php			import DB_PHP
from src.system.db.db_ssl			import DB_SSL

from src.system.db.db_admin			import DB_ADMIN
from src.system.db.db_admin_ruler	import DB_ADMIN_RULER

from multiprocessing.shared_memory	import ShareableList


class ThreadBaseServer(ThreadingMixIn, HTTPServer): ...

def process_backup():
	datetime_run			= datetime.now()
	while True:
		try:
			if (datetime.now() - datetime_run).days	> 0:
				# thực hiện đồng bộ log
				LOG.backup()
				ACCESS.backup()
				# thực hiện đồng bộ dữ liệu toàn hệ thống
				BACKUP.all()
				# cập nhật lại thông tin 
				datetime_run		= datetime.now()
			# wait time
			time.sleep(60 * 30)
		except Exception as e:
			_, _, exc_tb = sys.exc_info()
			fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
			LOG.append(str(e) + "\tFile: " + fname + "\tLine: " + str(exc_tb.tb_lineno))
			return

try:
	# thực hiện chạy tiến trình backup
	p_backup		= Process(target=process_backup)
	p_backup.start()
	# khởi tạo tiến trình chạy tạo chứng chỉ
	# 0				là cờ kiểm tra khối tạo chứng chỉ có đang được sử dụng ko
	# 1				là giá trị để khối kiểm tra có quyết định chạy hay dừng
	#				- 0:	trang thai khoi tao.
	#				- 1:	trang thai cho.
	#				- 2:	xac thuc thanh cong.
	#				- 3:	xac thuc khong thanh cong.
	# 2				là dữ liệu token để dùng xác thực.
	# 3				là domain cần để tạo chứng chỉ
	# 4				co cap nhat du lieu True du lieu da cap nhat False
	# 5				đường dẫn tới thư mục chứa chứng chỉ
	shm_share_list			= ShareableList([False, 0, 
								   "00000000000000000000000000000000000000000000000000", 
								   "0000000000000000000000000000000000000000",
								   False,
								   "000000000000000000000000000000000000000000000000000000000000"
								   ])
	id_memory_share			= shm_share_list.shm.name
	CERT.ID_MEMORY_SHARED	= id_memory_share

	p_certificate	= Process(target=CERT.run, args=(id_memory_share, ))
	p_certificate.start()
	# khi chương trình chạy thực hiện ghi lại các thông tin của chương trình trong access.log
	now				= datetime.now().strftime("%Y-%m-%d %H:%M:%S")
	ACCESS.append(f"===> start on {now}.")
	ACCESS.append(f"software version: {VERSION}")
	ACCESS.append(f"process main on {os.getpid()}.")
	ACCESS.append(f"process backup on {p_backup.pid}.")
	# thực hiện kiểm tra trạng thái của các dịch vụ liên quan
	ACCESS.append(f"check NGINX service: {NGINX.status()}.")
	ACCESS.append(f"check FTP service: {FTP.status()}.")
	ACCESS.append(f"check MYSQL service: {MYSQL.status()}.")
	# kiểm tra dịch vụ của các php-fpm
	for version in PHP_CONFIGURE.VERSIONS:
		ACCESS.append(f"check PHP-FPM version {version} service: {PHP_CONFIGURE.status(version)}.")

	# thực hiện liên kết tới CSDL MYSQL
	MYSQL.MS_connection	= MYSQL.connection(host="localhost", user="ubuntu", password="Admin1234@")
	# tạo luồng để duy trì kết nối
	# load thông tin customer
	db_user			= DB_USER()
	db_hosting		= DB_HOSTING()

	DB_FEATURE()
	DB_DATABASE()
	DB_DOMAIN()
	
	DB_PHP()
	DB_SSL()

	DB_ADMIN()
	DB_ADMIN_RULER()

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
	# sslcontext			= ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
	sslcontext.load_cert_chain(
		keyfile			= PATH_CERT_SUBDOMAIN_KEY,
		certfile		= PATH_CERT_SUBDOMAIN_FILE
	)
	server.socket		= sslcontext.wrap_socket(server.socket, server_side=True)
	server.serve_forever()
	
	p_backup.kill()
	p_certificate.kill()

	shm_share_list.shm.close()
except Exception as e:
	_, _, exc_tb = sys.exc_info()
	fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
	LOG.append(str(e) + "\tFile: " + fname + "\tLine: " + str(exc_tb.tb_lineno))
	# đóng kết nối tới csdl
	MYSQL.MS_connection.close()
	sys.exit(0)