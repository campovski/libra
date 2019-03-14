import serial
import sys


if __name__ =="__main__":
    ser = None
    try:
        ser = serial.Serial(
            port="COM16",
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

    str_write = "I4\r\n"
    ser.write(str_write.encode("ascii"))
    str_read = ser.read_until(expected=serial.CR+serial.LF)
    if isinstance(str_read, bytes):
        str_read = str_read.decode("ascii")
    print(str_read)