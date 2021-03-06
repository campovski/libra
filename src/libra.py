import serial
import sys
import threading
import queue
import datetime
import subprocess
import requests
import time


# Commands
CMD_CONT_READ = "SIR\r\n".encode("ascii")
CMD_SET_TARE = "T\r\n".encode("ascii")
CMD_CALIBRATE_SETTINGS = "C0\r\n".encode("ascii")
CMD_CALIBRATE_SET_SETTINGS = "C0 0 1\r\n".encode("ascii")
CMD_CALIBRATE_INIT_CALIB = "C2\r\n".encode("ascii")

# Return options
STABLE = "S"
UNSTABLE = "SD"

# Files
COUNTING_FILE = "counting.csv"
ALL_FILE = "data.csv"

# Units
GRAM = "g"

# NaN used for stabilization time while unstable
NAN = float("nan")

# Used for determining which type of counting a user wants
COUNT_ROW = "in_row"
COUNT_ONCE = "once"

class Libra():

	ser = None  # serial to communicate with libra
	mutex = None  # lock for serial port availability

	thread_cont_read = None  # thread for constant reading
	thread_writefile = None  # thread for writing data to file, should always be running

	queue_cont_read = None  # queue for storing SIR weight data
	queue_backup = queue.Queue()  # same as queue_cont_read but only GUI can empty
	queue_special = None  # used for anything else
	queue_writefile = None  # queue for writing data to file

	env_data = None  # stores a dictionary of environment data (humidity, temperature, and pressure)

	# Custom signals
	STOP_COUNTING = False
	STOP_MAIN = False
	STOP_WRITE = False


	def __init__(self, port=None, baudrate=None, bytesize=None, parity=None, stopbits=None, xonxoff=None):
		self.current_tare = 0.00  # current tare setting

		self.stabilization_time = NAN  # time from first UNSTABLE to first STABLE, initially on 0
		self.stabilization_time_start = None  # time of first UNSTABLE

		self.count_results_row = 0  # Used for getting results of counting, either number of pieces in a row or at once present
		self.count_results_once = 0
		self.target = ""
		self.all_file = ALL_FILE
		self.queue_stdout = queue.Queue()

		if port is not None:
			try:
				self.openSerial(port, baudrate, bytesize, parity, stopbits, xonxoff)
			except:
				self.queue_stdout.put("Serial port error")

		self.queue_cont_read = queue.Queue()
		self.queue_backup = queue.Queue()
		self.queue_writefile = queue.Queue()
		self.thread_writefile = threading.Thread(
			target=self.writefile,
			name="writefile",
			daemon=True
		)
		self.thread_writefile.start()

		self.getEnvData()


	def __str__(self):
		self.queue_stdout.put("Libra on port {0} with following configuration:\n\
               \tPORT = {1}\n\
               \tBAUDRATE = {2}\n\
               \tBYTESIZE = {3}\n\
               \tPARITY = {4}\n\
               \tSTOPBITS = {5}\n\
               \tXONXOFF = {6}\n")


	def getEnvData(self, p="Zračni tlak:  ", h="Vlažnost zraka: ", t="LJUBLJANA: "):
		data = requests.get(
			"http://meteo.arso.gov.si/uploads/probase/www/observ/surface/text/sl/observationAms_LJUBL-ANA_BEZIGRAD_latest.rss")
		env_data = {}
		i = data.text.find(p)
		env_data["pressure"] = data.text[i + len(p):i + len(p) + 4] + " mbar"

		i = data.text.find(h)
		env_data["humidity"] = data.text[i + len(h):i + len(h) + 2] + " %"

		i = data.text.find(t)
		env_data["temperature"] = data.text[i + len(t):i + len(t) + 2] + " °C"

		self.env_data = env_data

		return env_data


	def __str__(self):
		self.queue_stdout.put("Libra on port {0} with following configuration:\n\
               \tPORT = {1}\n\
               \tBAUDRATE = {2}\n\
               \tBYTESIZE = {3}\n\
               \tPARITY = {4}\n\
               \tSTOPBITS = {5}\n\
               \tXONXOFF = {6}\n")


	def openSerial(self, port, baudrate, bytesize, parity, stopbits, xonxoff):
		self.ser = serial.Serial(
			port=port,
			baudrate=baudrate,
			bytesize=bytesize,
			parity=parity,
			stopbits=stopbits,
			xonxoff=xonxoff
		)

		self.current_tare = 0 #self.getTareFromScale()  # get initial tare value
		self.mutex = threading.Lock()
		self.startReadCont()


	def startReadCont(self):
		self.STOP_MAIN = False
		assert self.ser is not None, "[startReadCont] Not connected to serial port"

		if self.thread_cont_read is None:
			self.thread_cont_read = threading.Thread(
				target=self.readCont,
				name="cont_read",
				daemon=True
			)

		self.mutex.acquire()
		self.thread_cont_read.start()  # when killing this process, release lock
		self.queue_stdout.put("thread_cont_read started!")


	def processRead(self, string):
		string = string.decode('ascii').strip().split()
		return [datetime.datetime.now().strftime("%m/%d/%Y, %H:%M:%S")] + string


	def readCont(self):
		self.ser.write(CMD_CONT_READ)

		while True:
			if self.STOP_MAIN:
				break
			now = datetime.datetime.now()
			str_read = self.ser.read_until(serial.CR+serial.LF)
			str_read = self.processRead(str_read)
			self.queue_cont_read.put(str_read)
			self.queue_backup.put(str_read)

			if self.stabilization_time_start is None and str_read[1] == UNSTABLE:
				self.stabilization_time = NAN
				self.stabilization_time_start = now
			elif str_read[1] == STABLE and self.stabilization_time_start is not None:
				timediff = now - self.stabilization_time_start
				self.stabilization_time_start = None
				self.stabilization_time = timediff.seconds + round(timediff.microseconds/10**6, 3)
				self.queue_writefile.put(str_read+[str(self.stabilization_time)]+[self.env_data["pressure"], self.env_data["humidity"], self.env_data["temperature"]])


	def countApi(self, method,stop=False,target=None):
		self.thread_count_stop = stop
		if stop:
			self.queue_stdout.put("[countApi] exit")
			return
		self.queue_stdout.put("[countApi] Starting thread with method " + method)
		if method == COUNT_ROW:
			self.thread_count = threading.Thread(target=self.countObjectsInRow,	name="countAPI", daemon=True)
		elif method == COUNT_ONCE:
			self.thread_count = threading.Thread(target=self.countObjectsAtOnce, name="countAPI", daemon=True, args=[target])
		else:
			self.queue_stdout.put("[countApi] Unknown method ...")
			return

		self.thread_count.start()


	def countObjectsInRow(self):
		self.queue_stdout.put("[countObjectsInRow] Waiting for stable zero ...")
		while not self.thread_count_stop:
			m = self.queue_cont_read.get()
			if m[1] == STABLE and float(m[2]) < 0.1:
				break

		self.queue_stdout.put("[countObjectsInRow] Stable zero acquired, start weighting ...")
		objects = []
		new = False
		while not self.thread_count_stop:
			if self.STOP_COUNTING or self.STOP_MAIN:
				break
			m = self.queue_cont_read.get()
			if m[1] == STABLE and new and float(m[2]) > 0.1:
				new = False
				objects.append(m)
				self.queue_stdout.put('beep')
			elif m[1] == UNSTABLE:
				new = True

		try:
			id_counting = str(int(subprocess.check_output(["tail", "-1", COUNTING_FILE]).split(',')[0])+1)
		except:
			id_counting = "0"

		f = open(COUNTING_FILE, mode="a+")
		for obj in objects:
			str_filewrite = id_counting + "," + ",".join(obj) + "\n"
			if f.write(str_filewrite) != len(str_filewrite):
				self.queue_stdout.put("[countObjectsInRow] failed to write object:\n\t{}\nto file".format(str_filewrite))
		f.close()

		self.count_results_row = len(objects)


	def countObjectsAtOnce(self, target_weight=None):
		self.target = None
		if target_weight is None:  # we need to get stable weight of an object unless it was already supplied
			self.queue_stdout.put("[countObjectsAtOnce] Waiting for stable weight ...")
			while True:
				m = self.queue_cont_read.get()
				if m[1] == STABLE and float(m[2]) > 0.1:
					self.target = float(m[2])
					break
		else:
			self.target = target_weight

		self.queue_stdout.put("[countObjectsAtOnce] Stable weight acquired, target weight is {0}".format(self.target))
		self.queue_stdout.put("[countObjectsAtOnce] Remove object and weight for stable zero ...")
		while True:
			m = self.queue_cont_read.get()
			if m[1] == STABLE and float(m[2]) < 0.1:
				break
		self.queue_stdout.put("[countObjectsAtOnce] Stable zero acquired. Put objects on weight")
		# weight will now become UNSTABLE due to change of pieces on scale
		weight = None
		while True:
			m = self.queue_cont_read.get()
			if m[1] == STABLE and float(m[2]) > 0.1:
				weight = float(m[2])
				break

		if weight is not None:
			self.queue_stdout.put("[countObjectsAtOnce] Counted {0} objects".format(weight/self.target))
			self.count_results_once = weight / self.target
		else:
			self.queue_stdout.put("[countObjectsAtOnce] Counting failed. Measured weight is None")
			self.count_results_once = None


	# Write to file on new stable weight.
	def writefile(self):
		while True:
			f = open(self.all_file, "a+")
			if self.STOP_WRITE:
				break
			m = self.queue_writefile.get()
			self.queue_stdout.put(m)
			str_filewrite = ",".join(m) + "\n"
			if f.write(str_filewrite) != len(str_filewrite):
				self.queue_stdout.put("[writefile] error writing to file")
			f.close()


	# API for setting tare value. If value and unit is not given, set tare to current value
	def setTare(self, zero=False):
		# signal to thread_read_cont to stop and acquire mutex
		self.stopReadCont()
		self.mutex.acquire()
		while not self.queue_cont_read.empty():
				self.queue_stdout.put(self.queue_cont_read.get())

		# Our scale only supports tare on next stable weight.
		self.ser.write(CMD_SET_TARE)


		# Response is "T S value unit". If not "S", something went wrong.
		response = self.ser.read_until(serial.CR+serial.LF).decode("ascii").strip()
		response_parts = response.split()
		if not zero:
			self.current_tare += float(response_parts[1])
			self.queue_stdout.put(self.current_tare)

		# release mutex and continue with continuous weight reading
		self.mutex.release()
		self.startReadCont()

	
	# Could be deprecated but we love to keep backward compatibility ;).
	def setZero(self):
		return self.setTare(0)


	# API for stoping writefile thread. Should not close this thread unless the end of the program.
	def stopWritefile(self):
		self.STOP_WRITE = True
		self.thread_writefile.join()
		caller = sys._getframe(1).f_code.co_name
		self.queue_stdout.put("[{0}] thread *writefile* joined!".format(caller))
		self.thread_writefile = None


	# API for stoping read_cont thread.
	def stopReadCont(self):
		self.STOP_MAIN = True
		self.thread_cont_read.join()
		# self.ser.write("@\r\n".encode("ascii"))
		self.mutex.release()
		caller = sys._getframe(1).f_code.co_name
		self.queue_stdout.put("[{0}] thread *read_cont* joined!".format(caller))
		self.thread_cont_read = None



if __name__ == "__main__":
	libra = Libra(
		port="/dev/ttyUSB0",
		baudrate=2400,
		bytesize=serial.SEVENBITS,
		parity=serial.PARITY_EVEN,
		stopbits=serial.STOPBITS_ONE,
		xonxoff=True
	)

	for thread in threading.enumerate():
		print("[main] Thread: " + thread.name)

	x = input("Press key to select option: ").strip()

	try:
		if x == "cr":
			libra.countObjectsInRow()
		elif x == "ca":
			tw = input("Target weight (None): ")
			if not tw:
				libra.countObjectsAtOnce()
			else:
				libra.countObjectsAtOnce(target_weight=float(tw))
		elif x == "calib":
			w = float(input("Weight for calibration: "))
			libra.calibrate(weight=w)
		elif x == "t":
			t = input("Tare: ")
			if not t:
				libra.setTare()
			else:
				libra.setTare(value=float(t))

		while True:
			pass
	except KeyboardInterrupt:
		libra.stopReadCont()
		libra.stopWritefile()
