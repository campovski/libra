import serial
import sys


if __name__ =="__main__":
    ser = None
    try:
        ser = serial.Serial(
            port="/dev/ttyUSB0",
            baudrate=2400,
            bytesize=serial.SEVENBITS,
            parity=serial.PARITY_EVEN,
            stopbits=serial.STOPBITS_ONE,
            xonxoff=True
        )
    except ValueError:
        print("Bad parameters in serial.Serial")
        sys.exit(1)
    except serial.SerialException:
        print("Cannot find device on given port")
        sys.exit(2)
    #str_write = "SIR\r\n"
    str_write = "SIR\r\n"
    ser.write(str_write.encode("ascii"))
    while True:
        #komanda = raw_input("vnesi komando: ")


        str_read = ser.read_until(serial.CR+serial.LF)
        if isinstance(str_read, bytes):
            str_read = str_read.decode("ascii")
        print(str_read)
