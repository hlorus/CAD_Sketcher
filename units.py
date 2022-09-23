# Code from MeasureIt_ARCH, see:
# https://github.com/kevancress/MeasureIt_ARCH/blob/development/measureit_arch_units.py

import math
import typing

import bpy
from bpy.props import EnumProperty

from .utilities.preferences import get_prefs

imperial_precision_prop = EnumProperty(
    items=(
        ("1", '1"', "1 Inch"),
        ("2", '1/2"', "1/2 Inch"),
        ("4", '1/4"', "1/4 Inch"),
        ("8", '1/8"', "1/8th Inch"),
        ("16", '1/16"', "1/16th Inch"),
        ("32", '1/32"', "1/32th Inch"),
        ("64", '1/64"', "1/64th Inch"),
    ),
    name="Imperial Precision",
    description="Measurement Precision for Imperial Units",
)

# Note: one Blender Unit (BU) is 1m
INCH_TO_CM = 2.54
INCHES_PER_FEET = 12
INCHES_PER_MILE = 5280 * INCHES_PER_FEET
THOU_PER_INCH = 1000
# Conversion factor from Blender Units to Inches / Feet
BU_TO_INCHES = 100.0 / INCH_TO_CM
BU_TO_FEET = 100.0 / (INCH_TO_CM * INCHES_PER_FEET)


def _inches_to_fraction(inches: float, precision: int) -> typing.Tuple[int, int, int]:
    """
    (Internal) Returns the integer and fractional part as a tuple of integer
    part, numerator and denominator (all integers), rounded to precision
    (expressed as 1/n'th of an inch).
    """
    inches_ = round(inches * int(precision)) / float(precision)
    frac, int_ = math.modf(inches_)
    num, denom = frac.as_integer_ratio()
    return (int(int_), num, denom)


def _format_metric_length(
    value: float, precision: int, unit_length: str = "METERS", hide_units: bool = False
) -> str:
    """
    (Internal) Format a value in BU/meters as a string
    """
    if unit_length == "CENTIMETERS":
        value *= 100
        unit = " cm"
    elif unit_length == "MILLIMETERS":
        value *= 1000
        unit = " mm"
    elif unit_length == "MICROMETERS":
        value *= 1000000
        unit = " µm"
    elif unit_length == "KILOMETERS":
        value = value / float(1000)
        unit = " km"
    else:
        unit = " m"
    return "{:.{}f}{}".format(value, precision, "" if hide_units else unit)


def _format_imperial_length(value, precision, unit_length="INCH") -> str:
    """
    (Internal) Format a length as a string using imperial units
    :param value: length in BU/meters
    :param type: float
    :param value: precision expressed as 1/n'th inch
    :param type: int
    :param unit_length: one of 'INCHES', 'FEET', 'MILES' or 'THOU'
    :param type: str
    """

    if unit_length in ("INCHES", "FEET"):
        value *= BU_TO_INCHES
        (inches, num, denom) = _inches_to_fraction(value, precision)
        if unit_length == "FEET":
            (feet, inches) = divmod(inches, INCHES_PER_FEET)
        else:
            feet = 0
        if feet > 0 and num > 0:
            return "{}′ {}-{}⁄{}″".format(feet, inches, num, denom)
        elif feet > 0:
            return "{}′ {}″".format(feet, inches)
        elif num > 0:
            return "{}-{}⁄{}″".format(inches, num, denom)
        else:
            return "{}″".format(inches)
    elif unit_length == "MILES":
        pass
    elif unit_length == "THOU":
        pass
    # Adaptive
    return bpy.utils.units.to_string(
        "IMPERIAL",
        "LENGTH",
        value,
        precision=precision,
        split_unit=False,
        compatible_unit=False,
    )


def format_distance(distance: float, hide_units=False, use_unit_scale=True) -> str:
    """
    Format a distance (length) for display
    :param area: distance in BU / meters
    :param type: float
    :returns: formatted string
    :return type: string
    """
    prefs = get_prefs()
    scene = bpy.context.scene
    unit_system = bpy.context.scene.unit_settings.system
    unit_length = scene.unit_settings.length_unit
    separate_units = scene.unit_settings.use_separate
    unit_scale = scene.unit_settings.scale_length
    if use_unit_scale:
        distance *= unit_scale
    if unit_system == "METRIC":
        precision = prefs.decimal_precision
        if not separate_units and not unit_length == "ADAPTIVE":
            return _format_metric_length(distance, precision, unit_length, hide_units)
        # If unit_length is 'Adaptive' or `separate_units` is True, use Blender
        # built-in which means units are always shown (regardless of
        # `hide_units`)
        return bpy.utils.units.to_string(
            "METRIC",
            "LENGTH",
            distance,
            precision=precision,
            split_unit=separate_units,
            compatible_unit=False,
        )

    elif unit_system == "IMPERIAL":
        if not unit_length == "ADAPTIVE":
            precision = prefs.imperial_precision
            return _format_imperial_length(distance, precision, unit_length)
        return bpy.utils.units.to_string(
            "IMPERIAL",
            "LENGTH",
            distance,
            split_unit=separate_units,
            compatible_unit=False,
        )

    return bpy.utils.units.to_string(
        "NONE", "LENGTH", distance, split_unit=separate_units, compatible_unit=False
    )


def format_angle(angle: float, hide_units=False) -> str:
    """
    Format an angle for display
    :param angle: angle in radians
    :type angle: float
    :returns: formatted string
    :return type: string
    """
    prefs = get_prefs()
    scene = bpy.context.scene
    precision = prefs.angle_precision
    system_rotation = scene.unit_settings.system_rotation

    if system_rotation == "DEGREES":
        return "{:.{}f}{}".format(
            math.degrees(angle), precision, "" if hide_units else "°"
        )
    elif system_rotation == "RADIANS":
        return "{:.{}f}{}".format(angle, precision, "" if hide_units else " rad")
