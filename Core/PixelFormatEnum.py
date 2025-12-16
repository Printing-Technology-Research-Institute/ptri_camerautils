from enum import Enum

class PixelFormatEnum(Enum):

    BGR8 = 0
    RGB8 = 1
    MONO8 = 2
    BayerGR8 = 3
    BayerBG8 = 4
    BayerRG8 = 5
    BayerGB8 = 6
    UNKNOWN = 7