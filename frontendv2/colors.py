#OLD CHART_COLORS = ['4e73df', '1cc88a', '36b9cc', '7dc5fe', 'cceecc']
# http://paletton.com/#uid=73y2l0kq7Bhf0HFkUCM-7CFGssV
# http://paletton.com/#uid=72z2l0kq7Bhf0HFkUCM-7CFGssV
CHART_COLORS = ['4987BB', '43C28C', '9DEB52', 'E3FA57', 'FF8859', 'FFB959', 'E85184', 'B143BC']
OTHER = 'dfdfdf'

# http://paletton.com/#uid=53D0i0ktVI-9wPvl2IuLjvVQznh
class MEMBER(object):
    BASE = "273ED1"
    COMMUNITY = "1D6ACD"
    STAFF = "11AAC7"
    BOT = "aeaeae"
    LIGHT = "A8B0E2"

    def __str__(self):
        return self.BASE

# https://paletton.com/#uid=13j0v0krxG389Q8jsHDIx-5O-oP
class ACTIVITY(object):
    BASE = "1CB6BD"
    LIGHT = "A5DADD"

    def __str__(self):
        return self.BASE

# https://paletton.com/#uid=1360v0krxG3e6M5lgHgHbFKKnrG
class CONVERSATION(object):
    BASE = "1CC88B"
    LIGHT = "98E2C8"

    def __str__(self):
        return self.BASE

# https://paletton.com/#uid=1150v0knWuSd-LwjkAKtortu+kD
class CONTRIBUTION(object):
    BASE = "f6c23e"
    LIGHT = 'FFE093'

    def __str__(self):
        return self.BASE

# https://paletton.com/#uid=c383R3j3A0kEaI4i9JdpVH0KcswNNlD
class LEVEL(object):
    CORE = '00C287'
    CONTRIBUTOR = '01B0B8'
    PARTICIPANT = '3579BF'
    VISITOR = '3D58C4'

    def __str__(self):
        return self.VISITOR
