import serial
import sys
import multiprocessing
import queue
import datetime
import subprocess

# Commands
CONT_READ = "SIR\r\n".encode('ascii')

# Return options
STABLE = "S"
UNSTABLE = "SD"

# Custom signals
STOP_PROCESS = "stop"  # put in appropriate queue to stop the process

# Files
COUNTING_FILE = "counting.csv"
ALL_FILE = "data.csv"


class Libra():

    ser = None  # serial to communicate with libra
    mutex = None  # lock for serial port availability

    thread_cont_read = None  # thread for constant weight printing
    thread_special = None  # thread for writing and reading special commands
    thread_writefile = None  # thread for writing data to file, should always be running

    queue_cont_read = None  # queue for storing SIR weight data
    queue_backup = None  # same as above but only GUI can empty
    queue_special = None  # used for anything else
    queue_writefile = None  # queue for writing data to file


    def __init__(self, port=None, baudrate=None, bytesize=None, parity=None, \
                 stopbits=None, xonxoff=None):
        if port is not None:
            self.open_serial(port, baudrate, bytesize, parity, stopbits, xonxoff)

        self.queue_cont_read = queue.Queue()
        self.queue_backup = queue.Queue()
        self.queue_writefile = queue.Queue()
        self.thread_writefile = multiprocessing.Process(
            target=self.writefile,
            daemon=True
        )


    def __str__(self):
        print("Libra on port {0} with following configuration:\n\
               \tPORT = {1}\n\
               \tBAUDRATE = {2}\n\
               \tBYTESIZE = {3}\n\
               \tPARITY = {4}\n\
               \tSTOPBITS = {5}\n\
               \tXONXOFF = {6}\n")


    def open_serial(self, port, baudrate, bytesize, parity, stopbits, xonxoff):
        self.ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=bytesize,
            parity=parity,
            stopbits=stopbits,
            xonxoff=xonxoff
        )
        self.mutex = multiprocessing.Lock()
        self.read_weight_cont()


    def read_weight_cont(self):
        assert self.ser is not None, "[read_weight_cont] Not connected to serial port"

        if self.thread_cont_read is None:
            self.thread_cont_read = multiprocessing.Process(
            target=read_cont,
            daemon=True
        )

        self.mutex.acquire()
        self.thread_cont_read.start()  # when killing this process, release lock


    def read_cont(self):
        f = open("measurements.csv", mode="a+")
        self.ser.write(CONT_READ)
        while True:
            str_read = self.ser.read_until(serial.CR+serial.LF)
            print(str_read.strip())
            str_read = str_read.decode('ascii').split()
            self.queue_cont_read.put(str_read)
            self.queue_backup.put(str_read)
            if str_read[0] == STABLE:
                str_read = [datetime.datetime.now()] + str_read
                # str_read.append(get_weather_data())
                self.queue_writefile.put(str_read)


    def counting_objects(self, force=False):
        print("[counting_objects] Waiting for stable zero ...")
        while True:
            m = self.queue_cont_read.get()
            if m[0] == STABLE and float(m[1]) < 0.1:
                break

        print("[counting_objects] Stable zero acquired, start weighting ...")
        objects = []
        new = False
        while True:
            m = self.queue_cont_read.get()
            if m == STOP_PROCESS:
                break
            if m[0] == STABLE and new and float(m[1]) > 0.1:
                new = False
                m = [datetime.datetime.now()] + m
                # m.append(get_weather_data())
                objects.append(m)
                print('\a')  # beep sound
            elif m[0] == UNSTABLE:
                new = True

        try:
            id_counting = str(int(subprocess.check_output(["tail", "-1", COUNTING_FILE]).split(',')[0])+1)
        except subprocess.CalledProcessError:
            id_counting = "0"

        f = open(COUNTING_FILE, mode="a+")
        for obj in objects:
            str_filewrite = id_counting + "," + ",".join(obj) + "\n"
            if f.write(str_filewrite) != len(str_filewrite):
                print("[counting_objects] failed to write object:\n\t{}\nto file".format(str_filewrite))
        f.close()

        return length(objects)


    # Write to file on new stable weight != 0.
    def writefile(self):
        f = open(ALL_FILE, "a+")
        while True:
            m = queue_writefile.get()
            if m == STOP_PROCESS:  # should only stop at the stop of execution
                break
            str_filewrite = ",".join(m) + "\n"
            if f.write(str_filewrite) != len(str_filewrite):
                print("[writefile] error writing to file")
        f.close()




        

            





        
    
