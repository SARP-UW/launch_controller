import socket


class SendNode:
    """
    SendNode provides a uniform format for sending telemetry.
    """
    def __init__(self, bind_addr, target_addr, codec):
        """
        bind_addr and target_addr are both a tuple of (ip, port). ip is '' for local ip.
        """
        self.codec = codec
        self.target_addr = target_addr
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(bind_addr)

    def shutdown(self):
        """
        Clean up socket resources.
        """
        self.sock.shutdown()
        self.sock.close()

    def send(self, msg):
        """
        We encode the argument msg, which is a list of values expected by the codec, and send it to
        the target address which is specified in the constructor in the form of tartget_addr.
        """
        self.sock.sendto(self.codec.encode(msg), self.target_addr)


class ReceiveNode:
    """
    ReceiveNode provides a uniform format for receiving telemetry.
    """
    def __init__(self, bind_addr, codec):
        """
        bind_addr is a tuple of (ip, port). ip is '' for local ip.
        """
        self.codec = codec
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(bind_addr)
        self.sock.setblocking(0)

    def shutdown(self):
        """
        Clean up socket resources.
        """
        self.sock.shutdown()
        self.sock.close()

    def receive(self):
        """
        Returns a tuple containing a list of data as defined in the codec and the source address.
        None is returned if there is no data.
        """
        try:
            data, server = self.sock.recvfrom(1024)
        except socket.error:
            return (None, None)
        return (self.codec.decode(data), server)
