# Struct is used to decode bytes into primitive data types.
import struct
# Queue is used as a thread safe data structure for packets to be sent to the client or server.
import queue

SERVER_QUEUE = queue.SimpleQueue()
CLIENT_QUEUE = queue.SimpleQueue()

def parse(data, port, origin):
    sign = '->' if origin == 'client' else '<-'
    print(f"c{sign}s: {data}")
    # Use structure below to drop packets if they contain certain data.
    #if data.find(b'insert packet here') >= 0:
    #   print("Dropped")
    #   return
    if (origin == 'client'):
        SERVER_QUEUE.put(data)
    elif (origin == 'server'):
        CLIENT_QUEUE.put(data)

