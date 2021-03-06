'''
Movers using wind as the forcing function
'''

import os
import copy
from datetime import datetime
import math

import numpy
np = numpy
from colander import (SchemaNode, Bool, String, Float, drop)

from gnome.basic_types import (ts_format,
                               world_point,
                               world_point_type,
                               velocity_rec,
                               datetime_value_2d)

from gnome.utilities import serializable, rand
from gnome.utilities import time_utils

from gnome import environment
from gnome.movers import CyMover, ProcessSchema
from gnome.cy_gnome.cy_wind_mover import CyWindMover
from gnome.cy_gnome.cy_gridwind_mover import CyGridWindMover
from gnome.cy_gnome.cy_ice_wind_mover import CyIceWindMover

from gnome.persist.base_schema import ObjType
from gnome.exceptions import ReferencedObjectNotSet


class WindMoversBaseSchema(ObjType, ProcessSchema):
    uncertain_duration = SchemaNode(Float(), missing=drop)
    uncertain_time_delay = SchemaNode(Float(), missing=drop)
    uncertain_speed_scale = SchemaNode(Float(), missing=drop)
    uncertain_angle_scale = SchemaNode(Float(), missing=drop)
    #extrapolate = SchemaNode(Bool(), missing=drop)


class WindMoverSchema(WindMoversBaseSchema):
    """
    Contains properties required by UpdateWindMover and CreateWindMover
    """
    # 'wind' schema node added dynamically
    name = 'WindMover'
    description = 'wind mover properties'
    extrapolate = SchemaNode(Bool(), missing=drop)


class WindMoversBase(CyMover):
    _state = copy.deepcopy(CyMover._state)
    _state.add(update=['uncertain_duration', 'uncertain_time_delay',
                       'uncertain_speed_scale', 'uncertain_angle_scale'],
               save=['uncertain_duration', 'uncertain_time_delay',
                     'uncertain_speed_scale', 'uncertain_angle_scale'])

    def __init__(self,
                 uncertain_duration=3,
                 uncertain_time_delay=0,
                 uncertain_speed_scale=2.,
                 uncertain_angle_scale=0.4,
                 #extrapolate=False,
                 **kwargs):
        """
        This is simply a base class for WindMover and GridWindMover for the
        common properties.

        The classes that inherit from this should define the self.mover object
        correctly so it has the required attributes.

        Input args with defaults:

        :param uncertain_duration: (seconds) the randomly generated uncertainty
            array gets recomputed based on 'uncertain_duration'
        :param uncertain_time_delay: when does the uncertainly kick in.
        :param uncertain_speed_scale: Scale for uncertainty in wind speed
            non-dimensional number
        :param uncertain_angle_scale: Scale for uncertainty in wind direction.
            Assumes this is in radians

        It calls super in the __init__ method and passes in the optional
        parameters (kwargs)
        """
        super(WindMoversBase, self).__init__(**kwargs)

        self.uncertain_duration = uncertain_duration
        self.uncertain_time_delay = uncertain_time_delay
        self.uncertain_speed_scale = uncertain_speed_scale

        # also sets self._uncertain_angle_units
        self.uncertain_angle_scale = uncertain_angle_scale

        #self.extrapolate = extrapolate

        self.array_types.update({'windages',
                                 'windage_range',
                                 'windage_persist'})

    # no conversion necessary - simply sets/gets the stored value
    uncertain_speed_scale = \
        property(lambda self: self.mover.uncertain_speed_scale,
                 lambda self, val: setattr(self.mover,
                                           'uncertain_speed_scale',
                                           val))
    uncertain_angle_scale = \
        property(lambda self: self.mover.uncertain_angle_scale,
                 lambda self, val: setattr(self.mover,
                                           'uncertain_angle_scale',
                                           val))

    def _seconds_to_hours(self, seconds):
        return seconds / 3600.0

    def _hours_to_seconds(self, hours):
        return hours * 3600.0

    @property
    def uncertain_duration(self):
        return self._seconds_to_hours(self.mover.uncertain_duration)

    @uncertain_duration.setter
    def uncertain_duration(self, val):
        self.mover.uncertain_duration = self._hours_to_seconds(val)

    @property
    def uncertain_time_delay(self):
        return self._seconds_to_hours(self.mover.uncertain_time_delay)

    @uncertain_time_delay.setter
    def uncertain_time_delay(self, val):
        self.mover.uncertain_time_delay = self._hours_to_seconds(val)

#     extrapolate = property(lambda self: self.mover.extrapolate,
#                            lambda self, val: setattr(self.mover,
#                                                      'extrapolate',
#                                                      val))

    def prepare_for_model_step(self, sc, time_step, model_time_datetime):
        """
        Call base class method using super
        Also updates windage for this timestep

        :param sc: an instance of gnome.spill_container.SpillContainer class
        :param time_step: time step in seconds
        :param model_time_datetime: current time of model as a date time object
        """
        super(WindMoversBase, self).prepare_for_model_step(sc, time_step,
                                                           model_time_datetime)

        # if no particles released, then no need for windage
        # TODO: revisit this since sc.num_released shouldn't be None
        if sc.num_released is None  or sc.num_released == 0:
            return

        rand.random_with_persistance(sc['windage_range'][:, 0],
                                     sc['windage_range'][:, 1],
                                     sc['windages'],
                                     sc['windage_persist'],
                                     time_step)

    def get_move(self, sc, time_step, model_time_datetime):
        """
        Override base class functionality because mover has a different
        get_move signature

        :param sc: an instance of the gnome.SpillContainer class
        :param time_step: time step in seconds
        :param model_time_datetime: current time of the model as a date time
                                    object
        """
        self.prepare_data_for_get_move(sc, model_time_datetime)

        if self.active and len(self.positions) > 0:
            self.mover.get_move(self.model_time,
                                time_step,
                                self.positions,
                                self.delta,
                                sc['windages'],
                                self.status_codes,
                                self.spill_type)

        return (self.delta.view(dtype=world_point_type)
                .reshape((-1, len(world_point))))

    def _state_as_str(self):
        '''
            Returns a string containing properties of object.
            This can be called by __repr__ or __str__ to display props
        '''
        info = ('  uncertain_duration={0.uncertain_duration}\n'
                '  uncertain_time_delay={0.uncertain_time_delay}\n'
                '  uncertain_speed_scale={0.uncertain_speed_scale}\n'
                '  uncertain_angle_scale={0.uncertain_angle_scale}\n'
                '  active_start time={0.active_start}\n'
                '  active_stop time={0.active_stop}\n'
                '  current on/off status={0.on}\n')
        return info.format(self)


class WindMover(WindMoversBase, serializable.Serializable):
    """
    Python wrapper around the Cython wind_mover module.
    This class inherits from CyMover and contains CyWindMover

    The real work is done by the CyWindMover object.  CyMover
    sets everything up that is common to all movers.
    """
    _state = copy.deepcopy(WindMoversBase._state)
    _state.add(update=['extrapolate'],
               save=['extrapolate'])
    _state.add_field(serializable.Field('wind', save=True, update=True,
                                        save_reference=True))
    _schema = WindMoverSchema

    def __init__(self, wind=None, extrapolate=False, **kwargs):
    #def __init__(self, wind=None, **kwargs):
        """
        Uses super to call CyMover base class __init__

        :param wind: wind object -- provides the wind time series for the mover

        Remaining kwargs are passed onto WindMoversBase __init__ using super.
        See Mover documentation for remaining valid kwargs.

        .. note:: Can be initialized with wind=None; however, wind must be
            set before running. If wind is not None, toggle make_default_refs
            to False since user provided a valid Wind and does not wish to
            use the default from the Model.
        """
        self.mover = CyWindMover()

        self._wind = None
        if wind is not None:
            self.wind = wind
            kwargs['make_default_refs'] = \
                kwargs.pop('make_default_refs', False)
            kwargs['name'] = \
                kwargs.pop('name', wind.name)

        self.extrapolate = extrapolate
        # set optional attributes
        super(WindMover, self).__init__(**kwargs)

		# this will have to be updated when wind is set or changed
        if self.wind is not None:
            self.real_data_start = time_utils.sec_to_datetime(self.wind.ossm.get_start_time())
            self.real_data_stop = time_utils.sec_to_datetime(self.wind.ossm.get_end_time())

    def __repr__(self):
        """
        .. todo::
            We probably want to include more information.
        """
        return ('{0.__class__.__module__}.{0.__class__.__name__}(\n'
                '{1}'
                ')'.format(self, self._state_as_str()))

    def __str__(self):
        info = ('WindMover - current _state. '
                'See "wind" object for wind conditions:\n'
                '{0}'.format(self._state_as_str()))
        return info


    extrapolate = property(lambda self: self.mover.extrapolate,
                           lambda self, val: setattr(self.mover,
                                                     'extrapolate',
                                                     val))

    @property
    def wind(self):
        return self._wind

    @wind.setter
    def wind(self, value):
        if not isinstance(value, environment.Wind):
            raise TypeError('wind must be of type environment.Wind')
        else:
            # update reference to underlying cython object
            self._wind = value
            self.mover.set_ossm(self.wind.ossm)

    def prepare_for_model_run(self):
        '''
        if wind attribute is not set, raise ReferencedObjectNotSet excpetion
        '''
        super(WindMover, self).prepare_for_model_run()

        if self.on and self.wind is None:
            msg = "wind object not defined for WindMover"
            raise ReferencedObjectNotSet(msg)

    def serialize(self, json_='webapi'):
        """
        Since 'wind' property is saved as a reference when used in save file
        and 'save' option, need to add appropriate node to WindMover schema
        """
        toserial = self.to_serialize(json_)
        schema = self.__class__._schema()
        if json_ == 'webapi':
            # add wind schema
            schema.add(environment.WindSchema(name='wind'))

        serial = schema.serialize(toserial)

        return serial

    @classmethod
    def deserialize(cls, json_):
        """
        append correct schema for wind object
        """
        schema = cls._schema()
        if 'wind' in json_:
            schema.add(environment.WindSchema())
        _to_dict = schema.deserialize(json_)

        return _to_dict


def wind_mover_from_file(filename, **kwargs):
    """
    Creates a wind mover from a wind time-series file (OSM long wind format)

    :param filename: The full path to the data file
    :param kwargs: All keyword arguments are passed on to the WindMover
        constructor

    :returns mover: returns a wind mover, built from the file
    """
    w = environment.Wind(filename=filename, format='r-theta')
    wm = WindMover(w, **kwargs)

    return wm


def constant_wind_mover(speed, direction, units='m/s'):
    """
    utility function to create a mover with a constant wind

    :param speed: wind speed
    :param direction: wind direction in degrees true
                  (direction from, following the meteorological convention)
    :param units='m/s': the units that the input wind speed is in.
                        options: 'm/s', 'knot', 'mph', others...

    :return: returns a gnome.movers.WindMover object all set up.

    .. note::
        The time for a constant wind timeseries is irrelevant. 
        This function simply sets it to datetime.now() accurate to hours.   
    """

    series = np.zeros((1, ), dtype=datetime_value_2d)

    # note: if there is ony one entry, the time is arbitrary
    dt = datetime.now().replace(microsecond=0, second=0, minute=0)
    series[0] = (dt, (speed, direction))
    wind = environment.Wind(timeseries=series, units=units)
    w_mover = WindMover(wind)
    return w_mover


class GridWindMoverSchema(WindMoversBaseSchema):
    """ Similar to WindMover except it doesn't have wind_id"""
    wind_file = SchemaNode(String(), missing=drop)
    topology_file = SchemaNode(String(), missing=drop)
    wind_scale = SchemaNode(Float(), missing=drop)
    extrapolate = SchemaNode(Bool(), missing=drop)


class GridWindMover(WindMoversBase, serializable.Serializable):
    _state = copy.deepcopy(WindMoversBase._state)
    _state.add(update=['wind_scale', 'extrapolate'], save=['wind_scale', 'extrapolate'])
    _state.add_field([serializable.Field('wind_file', save=True,
                    read=True, isdatafile=True, test_for_eq=False),
                    serializable.Field('topology_file', save=True,
                    read=True, isdatafile=True, test_for_eq=False)])

    _schema = GridWindMoverSchema

    def __init__(self, wind_file, topology_file=None,
                 extrapolate=False, time_offset=0,
                 **kwargs):
        """
        :param wind_file: file containing wind data on a grid
        :param topology_file: Default is None. When exporting topology, it
                              is stored in this file
        :param wind_scale: Value to scale wind data
        :param extrapolate: Allow current data to be extrapolated before and
                            after file data
        :param time_offset: Time zone shift if data is in GMT

        Pass optional arguments to base class
        uses super: super(GridWindMover,self).__init__(\*\*kwargs)
        """

        if not os.path.exists(wind_file):
            raise ValueError('Path for wind file does not exist: {0}'
                             .format(wind_file))

        if topology_file is not None:
            if not os.path.exists(topology_file):
                raise ValueError('Path for Topology file does not exist: {0}'
                                 .format(topology_file))

        # is wind_file and topology_file is stored with cy_gridwind_mover?
        self.wind_file = wind_file
        self.topology_file = topology_file
        self.mover = CyGridWindMover(wind_scale=kwargs.pop('wind_scale', 1))
        self.name = os.path.split(wind_file)[1]
        super(GridWindMover, self).__init__(**kwargs)

        self.mover.text_read(wind_file, topology_file)
        self.real_data_start = time_utils.sec_to_datetime(self.mover.get_start_time())
        self.real_data_stop = time_utils.sec_to_datetime(self.mover.get_end_time())
        self.mover.extrapolate_in_time(extrapolate)
        self.mover.offset_time(time_offset * 3600.)

    def __repr__(self):
        """
        .. todo::
            We probably want to include more information.
        """
        info = 'GridWindMover(\n{0})'.format(self._state_as_str())
        return info

    def __str__(self):
        info = ('GridWindMover - current _state.\n'
                '{0}'.format(self._state_as_str()))
        return info

    wind_scale = property(lambda self: self.mover.wind_scale,
                          lambda self, val: setattr(self.mover,
                                                    'wind_scale',
                                                    val))

    extrapolate = property(lambda self: self.mover.extrapolate,
                           lambda self, val: setattr(self.mover,
                                                     'extrapolate',
                                                     val))

    time_offset = property(lambda self: self.mover.time_offset / 3600.,
                           lambda self, val: setattr(self.mover,
                                                     'time_offset',
                                                     val * 3600.))

    def export_topology(self, topology_file):
        """
        :param topology_file=None: absolute or relative path where topology
                                   file will be written.
        """
        if topology_file is None:
            raise ValueError('Topology file path required: {0}'.
                             format(topology_file))

        self.mover.export_topology(topology_file)

    def extrapolate_in_time(self, extrapolate):
        """
        :param extrapolate=false: Allow current data to be extrapolated before
                                  and after file data.
        """
        self.mover.extrapolate_in_time(extrapolate)

    def offset_time(self, time_offset):
        """
        :param offset_time=0: Allow data to be in GMT with a time zone offset
                              (hours).
        """
        self.mover.offset_time(time_offset * 3600.)

    def get_start_time(self):
        """
        :this will be the real_data_start time (seconds).
        """
        return (self.mover.get_start_time())

    def get_end_time(self):
        """
        :this will be the real_data_stop time (seconds).
        """
        return (self.mover.get_end_time())

class IceWindMoverSchema(WindMoversBaseSchema):
    filename = SchemaNode(String(), missing=drop)
    topology_file = SchemaNode(String(), missing=drop)
    #current_scale = SchemaNode(Float(), missing=drop)
    #extrapolate = SchemaNode(Bool(), missing=drop)


class IceWindMover(WindMoversBase, serializable.Serializable):

    #_update = ['wind_scale', 'extrapolate']               
    #_save = ['wind_scale', 'extrapolate']             
    _state = copy.deepcopy(WindMoversBase._state)

    #_state.add(update=_update, save=_save)
    _state.add_field([serializable.Field('filename',
                                         save=True, read=True, isdatafile=True,
                                         test_for_eq=False),
                      serializable.Field('topology_file',
                                         save=True, read=True, isdatafile=True,
                                         test_for_eq=False)])
    _schema = IceWindMoverSchema

    def __init__(self, filename,
                 topology_file=None,
                 extrapolate=False,
                 time_offset=0,
                 **kwargs):
        """
        Initialize an IceWindMover

        :param filename: absolute or relative path to the data file:
                         could be netcdf or filelist
        :param topology_file=None: absolute or relative path to topology file.
                                   If not given, the IceMover will
                                   compute the topology from the data file.
        :param active_start: datetime when the mover should be active
        :param active_stop: datetime after which the mover should be inactive
        :param wind_scale: Value to scale wind data
        :param extrapolate: Allow current data to be extrapolated
                            before and after file data
        :param time_offset: Time zone shift if data is in GMT

        uses super, super(IceWindMover,self).__init__(\*\*kwargs)
        """

        # NOTE: will need to add uncertainty parameters and other dialog fields
        #       use super with kwargs to invoke base class __init__

        # if child is calling, the self.mover is set by child - do not reset
        if type(self) == IceWindMover:
            self.mover = CyIceWindMover()

        if not os.path.exists(filename):
            raise ValueError('Path for current file does not exist: {0}'
                             .format(filename))

        if topology_file is not None:
            if not os.path.exists(topology_file):
                raise ValueError('Path for Topology file does not exist: {0}'
                                 .format(topology_file))

        # check if this is stored with cy_ice_wind_mover?
        self.filename = filename
        self.name = os.path.split(filename)[1]

        # check if this is stored with cy_ice_wind_mover?
        self.topology_file = topology_file

        self.mover.text_read(filename, topology_file)
        self.extrapolate = extrapolate
        self.mover.extrapolate_in_time(extrapolate)
        self.mover.offset_time(time_offset * 3600.)

        super(IceWindMover, self).__init__(**kwargs)

    def __repr__(self):
        return ('IceWindMover('
                'active_start={1.active_start}, '
                'active_stop={1.active_stop}, '
                'on={1.on})'.format(self.mover, self))

    def __str__(self):
        return ('IceWindMover - current _state.\n'
                '  active_start time={1.active_start}\n'
                '  active_stop time={1.active_stop}\n'
                '  current on/off status={1.on}'
                .format(self.mover, self))

    # Define properties using lambda functions: uses lambda function, which are
    # accessible via fget/fset as follows:
#     current_scale = property(lambda self: self.mover.current_scale,
#                              lambda self, val: setattr(self.mover,
#                                                        'current_scale',
#                                                        val))
# 
#     extrapolate = property(lambda self: self.mover.extrapolate,
#                            lambda self, val: setattr(self.mover,
#                                                      'extrapolate',
#                                                      val))
# 
#     time_offset = property(lambda self: self.mover.time_offset / 3600.,
#                            lambda self, val: setattr(self.mover,
#                                                      'time_offset',
#                                                      val * 3600.))
# 
    def get_grid_data(self):
        if self.mover._is_triangle_grid():
            return self.get_triangles()
        else:
            return self.get_cells()

    def get_center_points(self):
        if self.mover._is_triangle_grid():
            return self.get_triangle_center_points()
        else:
            return self.get_cell_center_points()

    def get_scaled_velocities(self, model_time):
        """
        :param model_time=0:
        """
        num_tri = self.mover.get_num_triangles()
        if self.mover._is_triangle_grid():
            num_cells = num_tri
        else:
            num_cells = num_tri / 2
        #vels = np.zeros(num_cells, dtype=basic_types.velocity_rec)
        vels = np.zeros(num_cells, dtype=velocity_rec)
        self.mover.get_scaled_velocities(model_time, vels)

        return vels

    def get_ice_velocities(self, model_time):
        """
        :param model_time=0:
        """
        num_tri = self.mover.get_num_triangles()
        #vels = np.zeros(num_tri, dtype=basic_types.velocity_rec)
        vels = np.zeros(num_tri, dtype=velocity_rec)
        self.mover.get_ice_velocities(model_time, vels)

        return vels

    def get_movement_velocities(self, model_time):
        """
        :param model_time=0:
        """
        num_tri = self.mover.get_num_triangles()
        #vels = np.zeros(num_tri, dtype=basic_types.velocity_rec)
        vels = np.zeros(num_tri, dtype=velocity_rec)
        self.mover.get_movement_velocities(model_time, vels)

        return vels

    def get_ice_fields(self, model_time):
        """
        :param model_time=0:
        """
        num_tri = self.mover.get_num_triangles()
        num_cells = num_tri / 2
        frac_coverage = np.zeros(num_cells, dtype=np.float64)
        thickness = np.zeros(num_cells, dtype=np.float64)
        self.mover.get_ice_fields(model_time, frac_coverage, thickness)

        return frac_coverage, thickness

    def export_topology(self, topology_file):
        """
        :param topology_file=None: absolute or relative path where
                                   topology file will be written.
        """
        if topology_file is None:
            raise ValueError('Topology file path required: {0}'
                             .format(topology_file))

        self.mover.export_topology(topology_file)

    def extrapolate_in_time(self, extrapolate):
        """
        :param extrapolate=false: allow current data to be extrapolated
                                  before and after file data.
        """
        self.mover.extrapolate_in_time(extrapolate)
        self.extrapolate = extrapolate

    def offset_time(self, time_offset):
        """
        :param offset_time=0: allow data to be in GMT with a time zone offset
                              (hours).
        """
        self.mover.offset_time(time_offset * 3600.)

    def get_offset_time(self):
        """
        :param offset_time=0: allow data to be in GMT with a time zone offset
                              (hours).
        """
        return (self.mover.get_offset_time()) / 3600.


