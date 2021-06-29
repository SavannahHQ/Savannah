#OLD CHART_COLORS = ['4e73df', '1cc88a', '36b9cc', '7dc5fe', 'cceecc']
# http://paletton.com/#uid=73y2l0kq7Bhf0HFkUCM-7CFGssV
# http://paletton.com/#uid=72z2l0kq7Bhf0HFkUCM-7CFGssV
CHART_COLORS = ['4987BB', '3AA8C7', '43C28C', '9DEB52', 'E3FA57', 'FFE758', 'FFB959', 'FF752F', 'F4556E', 'E866B5', 'C16DCA', '8A79D6']
TAG_COLORS = [
 '800000', #maroon
 '8B0000', #dark red
 'A52A2A', #brown
 'B22222', #firebrick
 'DC143C', #crimson
 'FF6347', #tomato
 'FF7F50', #coral
 'CD5C5C', #indian red
 'F08080', #light coral
 'E9967A', #dark salmon
 'FA8072', #salmon
 'FFA07A', #light salmon
 'FF4500', #orange red
 'FF8C00', #dark orange
 'FFA500', #orange
 'FFD700', #gold
 'B8860B', #dark golden rod
 'DAA520', #golden rod
 'EEE8AA', #pale golden rod
 'BDB76B', #dark khaki
 'F0E68C', #khaki
 'FFFF00', #yellow
 '9ACD32', #yellow green
 '7CFC00', #lawn green
 '7FFF00', #chart reuse
 'ADFF2F', #green yellow
 '006400', #dark green
 '008000', #green
 '228B22', #forest green
 '00FF00', #lime
 '32CD32', #lime green
 '90EE90', #light green
 '98FB98', #pale green
 '00FA9A', #medium spring green
 '00FF7F', #spring green
 '2E8B57', #sea green
 '66CDAA', #medium aqua marine
 '3CB371', #medium sea green
 '20B2AA', #light sea green
 '2F4F4F', #dark slate gray
 '008080', #teal
 '008B8B', #dark cyan
 '00FFFF', #aqua
 '00FFFF', #cyan
 'E0FFFF', #light cyan
 '00CED1', #dark turquoise
 '40E0D0', #turquoise
 '48D1CC', #medium turquoise
 'AFEEEE', #pale turquoise
 '7FFFD4', #aqua marine
 'B0E0E6', #powder blue
 '4682B4', #steel blue
 '6495ED', #corn flower blue
 '00BFFF', #deep sky blue
 '1E90FF', #dodger blue
 'ADD8E6', #light blue
 '87CEEB', #sky blue
 '87CEFA', #light sky blue
 '191970', #midnight blue
 '000080', #navy
 '00008B', #dark blue
 '0000CD', #medium blue
 '0000FF', #blue
 '4169E1', #royal blue
 '8A2BE2', #blue violet
 '4B0082', #indigo
 '483D8B', #dark slate blue
 '6A5ACD', #slate blue
 '7B68EE', #medium slate blue
 '9370DB', #medium purple
 '8B008B', #dark magenta
 '9400D3', #dark violet
 '9932CC', #dark orchid
 'BA55D3', #medium orchid
 '800080', #purple
 'DDA0DD', #plum
 'EE82EE', #violet
 'FF00FF', #magenta / fuchsia
 'DA70D6', #orchid
 'C71585', #medium violet red
 'DB7093', #pale violet red
 'FF1493', #deep pink
 'FF69B4', #hot pink
 'FFB6C1', #light pink
 'FFC0CB', #pink
 'FAEBD7', #antique white
 'F5F5DC', #beige
 'FFE4C4', #bisque
 'FFEBCD', #blanched almond
 'F5DEB3', #wheat
 'FFF8DC', #corn silk
 'FFFACD', #lemon chiffon
 'FAFAD2', #light golden rod yellow
 'FFFFE0', #light yellow
 '8B4513', #saddle brown
 'A0522D', #sienna
 'D2691E', #chocolate
 'CD853F', #peru
 'F4A460', #sandy brown
 'DEB887', #burly wood
 'D2B48C', #tan
 'FFE4B5', #moccasin
 'FFDEAD', #navajo white
 'FFDAB9', #peach puff
 'FFE4E1', #misty rose
 'FFF0F5', #lavender blush
 'FAF0E6', #linen
 'FDF5E6', #old lace
 'FFEFD5', #papaya whip
 'FFF5EE', #sea shell
 'F5FFFA', #mint cream
 'B0C4DE', #light steel blue
 'E6E6FA', #lavender
 'FFFAF0', #floral white
 'F0F8FF', #alice blue
 'F8F8FF', #ghost white
 'F0FFF0', #honeydew
 'FFFFF0', #ivory
 'F0FFFF', #azure
]

OTHER = 'dfdfdf'

# http://paletton.com/#uid=53D0i0ktVI-9wPvl2IuLjvVQznh
class MEMBER(object):
    BASE = "273ED1"
    COMMUNITY = "1D6ACD"
    STAFF = "11AAC7"
    BOT = "aeaeae"
    LIGHT = "A8B0E2"
    JOINED = '4987BB'
    ACTIVE = "1CB6BD"
    RETURNING = '3bdb61'

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
