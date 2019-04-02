import serial
import sys
import threading
import queue
import datetime
import subprocess
import requests


# Commands
CMD_CONT_READ = "SIR\r\n".encode('ascii')
CMD_SET_TARE_CURR = "TA\r\n".encode('ascii')
CMD_SET_TARE = "TA"
CMD_GET_TARE = None  # TODO
CMD_CALIBRATE = None

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


class Libra():

    ser = None  # serial to communicate with libra
    mutex = None  # lock for serial port availability

    thread_cont_read = None  # thread for constant reading
    thread_writefile = None  # thread for writing data to file, should always be running

    queue_cont_read = None  # queue for storing SIR weight data
    queue_backup = queue.Queue()  # same as queue_cont_read but only GUI can empty
    queue_special = None  # used for anything else
    queue_writefile = None  # queue for writing data to file

    current_tare = None  # current tare setting

    stabilization_time = 0.000  # time from first UNSTABLE to first STABLE, initially on 0
    stabilization_time_start = None  # time of first UNSTABLE

    # Custom signals
    STOP_COUNTING = False
    STOP_MAIN = False
    STOP_WRITE = False


    def __init__(self, port=None, baudrate=None, bytesize=None, parity=None, stopbits=None, xonxoff=None):
        if port is not None:
            self.openSerial(port, baudrate, bytesize, parity, stopbits, xonxoff)

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

        return env_data


    def openSerial(self, port, baudrate, bytesize, parity, stopbits, xonxoff):
        self.ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=bytesize,
            parity=parity,
            stopbits=stopbits,
            xonxoff=xonxoff
        )

        self.current_tare = self.getTareFromScale()  # get initial tare value
        self.mutex = threading.Lock()
        self.startReadCont()


    def startReadCont(self):
        assert self.ser is not None, "[startReadCont] Not connected to serial port"

        if self.thread_cont_read is None:
            self.thread_cont_read = threading.Thread(
            target=self.readCont,
            name="cont_read",
            daemon=True
        )

        self.mutex.acquire()
        self.thread_cont_read.start()  # when killing this process, release lock
        print("thread_cont_read started!")


    def processRead(self, string):
        string = string.decode('ascii').strip().split()
        return [datetime.datetime.now()] + string #+ self.getEnvData()


    def readCont(self):
        self.ser.write(CMD_CONT_READ)

        while True:
            if self.STOP_MAIN:
                break
            now = datetime.datetime.now()
            str_read = self.ser.read_until(serial.CR+serial.LF)
            now = (now + datetime.datetime.now()) / 2  # take mid time
            str_read = self.processRead(str_read)
            self.queue_cont_read.put(str_read)
            self.queue_backup.put(str_read)

            if str_read[1] == STABLE:
                # TODO refresh stabilization time in UI
                timediff = now - self.stabilization_time_start
                self.stabilization_time_start = None
                self.stabilization_time = timediff.seconds + round(timediff.microseconds/10**6, 3)

                self.queue_writefile.put(str_read+[self.stabilization_time])
            elif stabilization_time_start is None:
                self.stabilization_time = NAN
                self.stabilization_time_start = now


    # THIS ONE IS NOT IN ITS OWN THREAD BECAUSE USER SHOULD STOP WEIGHTING MANUALLY!
    def countObjectsInRow(self):
        print("[countObjectsInRow] Waiting for stable zero ...")
        while True:
            m = self.queue_cont_read.get()
            if m[1] == STABLE and float(m[2]) < 0.1:
                break

        print("[countObjectsInRow] Stable zero acquired, start weighting ...")
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
                print("[countObjectsInRow] failed to write object:\n\t{}\nto file".format(str_filewrite))
        f.close()

        return len(objects)


    # THIS ONE IS NOT IN ITS OWN THREAD BECAUSE USER SHOULD STOP WEIGHTING MANUALLY!
    # TODO UI: Inform user to put an object on the scale if not called with target_weight.
    # Run this function after user presses ok.
    def countObjectsAtOnce(self, target_weight=None):
        target = None
        if target_weight is None:  # we need to get stable weight of an object
            print("[countObjectsAtOnce] Waiting for stable weight ...")
            while True:
                m = self.queue_cont_read.get()
                if m[1] == STABLE:
                    target = float(m[2])
                    break
        else:
            target = target_weight

        print("[countObjectsAtOnce] Stable weight acquired, target weight is {0}".format(target))
        # weight will now become UNSTABLE due to change of pieces on scale
        weight = None
        while True:
            m = self.queue_cont_read.get()
            if m[1] == STABLE and float(m[2]) > 0.1:
                weight = float(m[2])
                break
        
        if weight is not None:
            print("[countObjectsAtOnce] Counted {0} objects".format(weight/target))
            return weight / target
        else:
            print("[countObjectsAtOnce] Counting failed. Measured weight is None")
            return None  


    # Write to file on new stable weight != 0.
    def writefile(self):
        f = open(ALL_FILE, "a+")
        while True:
            if self.STOP_WRITE:
                break
            m = self.queue_writefile.get()
            str_filewrite = ",".join(m) + "\n"
            if f.write(str_filewrite) != len(str_filewrite):
                print("[writefile] error writing to file")
        f.close()

    
    # API for setting tare value. If value and unit is not given, set tare to current value
    def setTare(self, value=None, unit=GRAM):
        # signal to thread_read_cont to stop and acquire mutex
        self.stopReadCont()
        self.mutex.acquire()

        if value == None:
            self.ser.write(CMD_SET_TARE_CURR)
        else:
            cmd = "{0} {1} {2}\r\n".format(CMD_SET_TARE, value, unit).encode('ascii')
            self.ser.write(cmd)

        self.current_tare = self.getTareFromScale()

        # release mutex and continue with continuous weight reading
        self.mutex.release()
        self.startReadCont()

    
    # TODO get current tare setting: correct CMD_GET_TARE
    def getTareFromScale(self):
        self.ser.write(CMD_GET_TARE)
        tare = self.ser.read_until(serial.CR+serial.LF)
        self.current_tare = float(tare)

  
    # TODO passes in weight for calibration
    def calibrate(self, weight, unit=GRAM):
        # signal to thread_read_cont to stop and acquire mutex
        self.stopReadCont()
        self.mutex.acquire()

        self.ser.write("{0} {1} {2}\r\n".format(CMD_CALIBRATE, weight, unit))
        
        # release mutex and continue weighting
        self.mutex.release()
        self.startReadCont()


    # API for stoping writefile thread. Should not close this thread unless the end of the program.
    def stopWritefile(self):
        self.STOP_WRITE = True
        self.thread_writefile.join()
        caller = sys._getframe(1).f_code.co_name
        print("[{0}] thread *writefile* joined!".format(caller))


    # API for stoping read_cont thread.
    def stopReadCont(self):
        self.STOP_MAIN = True
        self.thread_cont_read.join()
        self.mutex.release()
        caller = sys._getframe(1).f_code.co_name
        print("[{0}] thread *read_cont* joined!".format(caller))
            



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








        

            





        
    
