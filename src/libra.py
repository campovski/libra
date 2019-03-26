import serial
import sys
import threading
import queue
import datetime
import subprocess

# Commands
CONT_READ = "SIR\r\n".encode('ascii')

# Return options
STABLE = "S"
UNSTABLE = "SD"

# Files
COUNTING_FILE = "counting.csv"
ALL_FILE = "data.csv"


class Libra():

    ser = None  # serial to communicate with libra
    mutex = None  # lock for serial port availability

    thread_cont_read = None  # thread for constant reading
    thread_writefile = None  # thread for writing data to file, should always be running

    queue_cont_read = None  # queue for storing SIR weight data
    queue_backup = None  # same as queue_cont_read but only GUI can empty
    queue_special = None  # used for anything else
    queue_writefile = None  # queue for writing data to file

    # Custom signals
    STOP_COUNTING = False
    STOP_MAIN = False


    def __init__(self, port=None, baudrate=None, bytesize=None, parity=None, \
                 stopbits=None, xonxoff=None):
        if port is not None:
            self.open_serial(port, baudrate, bytesize, parity, stopbits, xonxoff)

        self.queue_cont_read = queue.Queue()
        self.queue_backup = queue.Queue()
        self.queue_writefile = queue.Queue()
        self.thread_writefile = threading.Thread(
            target=self.writefile,
            name="writefile",
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
        self.mutex = threading.Lock()
        self.read_weight_cont()


    def read_weight_cont(self):
        assert self.ser is not None, "[read_weight_cont] Not connected to serial port"

        if self.thread_cont_read is None:
            self.thread_cont_read = threading.Thread(
            target=read_cont,
            name="cont_read",
            daemon=True
        )

        self.mutex.acquire()
        self.thread_cont_read.start()  # when killing this process, release lock
        print("thread_cont_read started!")


    def read_cont(self):
        def process_read(string):
            string = string.decode('ascii').strip().split()
            return [datetime.datetime.now()] + string + self.get_weather_data()

        self.ser.write(CONT_READ)
        while True:
            if self.STOP_MAIN:
                break
            str_read = self.ser.read_until(serial.CR+serial.LF)
            str_read = self.process_read(str_read)
            self.queue_cont_read.put(str_read)
            self.queue_backup.put(str_read)
            if str_read[1] == STABLE:
                self.queue_writefile.put(str_read)        


    def counting_objects(self):
        print("[counting_objects] Waiting for stable zero ...")
        while True:
            m = self.queue_cont_read.get()
            if m[1] == STABLE and float(m[2]) < 0.1:
                break

        print("[counting_objects] Stable zero acquired, start weighting ...")
        objects = []
        new = False
        while True:
            if self.STOP_COUNTING or self.STOP_MAIN:
                break
            m = self.queue_cont_read.get()
            if m[1] == STABLE and new and float(m[2]) > 0.1:
                new = False
                objects.append(m)
                print('\a')  # beep sound
            elif m[1] == UNSTABLE:
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
            if self.STOP_MAIN:
                break
            m = queue_writefile.get()
            str_filewrite = ",".join(m) + "\n"
            if f.write(str_filewrite) != len(str_filewrite):
                print("[writefile] error writing to file")
        f.close()

    
    def get_weather_data(self):
        return ["not_yet_implemented"]


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
        if x == "c":
            libra.counting_objects()
        while True:
            pass
    except KeyboardInterrupt:
        libra.STOP_MAIN = True
        libra.thread_cont_read.join()
        print("[main] thread *cont_read* joined!")
        libra.thread_writefile.join()
        print("[main] thread *writefile* joined")








        

            





        
    
