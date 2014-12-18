#!/usr/bin/env python

"""
test code for the wave calculations
"""

import datetime
import numpy as np

from gnome.environment import waves
from gnome.environment import wind
from gnome.basic_types import datetime_value_2d

import pytest

# some test setup

start_time = datetime.datetime(2014, 12, 1, 0)
series = np.array((start_time, (10, 45)),
                      dtype=datetime_value_2d).reshape((1, ))
test_wind = wind.Wind(timeseries=series, units='meter per second')

def test_init():
    w = waves.Waves(wind)

    # just to assert something
    assert type(w) == waves.Waves

def test_compute_H():
    """can it compute a wave height at all?

       fetch unlimited
    """
    w = waves.Waves(wind)
    H = w.compute_H(5) # five m/s wind

    print H

    ## I have no idea what the answers _should_ be
    #assert H == 0

def test_compute_H_fetch():
    """can it compute a wave height at all?

       fetch limited case
    """
    w = waves.Waves(wind, fetch=10000) # 10km
    H = w.compute_H(5) # five m/s wind

    print H

    #assert H == 0

def test_compute_H_fetch_huge():
    """
    With a huge fetch, should be same as fetch-unlimited
    """
    w = waves.Waves(wind, fetch=1e100) #
    H_f = w.compute_H(5) # five m/s wind
    w.fetch = None
    H_nf = w.compute_H(5)


    assert H_f == H_nf


@pytest.mark.parametrize("U", [1.0, 2.0, 4.0, 8.0, 16.0, 32.0])
def test_psuedo_wind(U):
    """
    should reverse the wave height computation

    at least for fetch-unlimited
    """
    w = waves.Waves(wind)

    print "testing for U:", U
    ## 0.707 compensates for RMS wave height
    assert round( w.comp_psuedo_wind ( w.compute_H(U) / 0.707 ), 5)  == round( U, 8 )

# note: 200 becuse that's when whitecap fraction would go above 1.0
@pytest.mark.parametrize("U", [0.0, 1.0, 2.0, 3.0, 4.0, 8.0, 16.0, 32.0, 200.0])
def test_whitecap_fraction(U):
    """
    should reverse the wave height computation

    at least for fetch-unlimited
    """
    w = waves.Waves(wind)

    print "testing for U:", U

    f = w.comp_whitecap_fraction(U)

    assert f >= 0.0
    assert f <= 1.0

    if U <= 3.0:
        assert f == 0.0

    ##fixme: add a value check???


@pytest.mark.parametrize("U", [0.0, 1.0, 2.0, 3.0, 4.0, 8.0, 16.0, 32.0])
def test_period(U):
    """
    test the wave period
    """
    w = waves.Waves(wind)

    print "testing for U:", U

    f = w.comp_period(U)

    print f
    assert False # what else to check for???

@pytest.mark.parametrize("U", [0.0, 1.0, 2.0, 3.0, 4.0, 8.0, 16.0, 32.0])
def test_period_fetch(U):
    """
    Test the wave period
    """
    w = waves.Waves(wind, fetch = 10000)# 10km fetch

    print "testing for U:", U

    T = w.comp_period(U)

    print T
    assert False # what else to check for???



