"""
interface with the NOAA Center for Operational Oceanographic Products and Services (CO-OPS) API
https://api.tidesandcurrents.noaa.gov/api/prod/
"""

from datetime import datetime
from enum import Enum
from functools import lru_cache
from typing import Union

import bs4
from bs4 import BeautifulSoup
import pandas
from pandas import DataFrame
import requests
from shapely.geometry import MultiPolygon, Point, Polygon


class COOPS_Product(Enum):
    WATER_LEVEL = (
        'water_level'
        # Preliminary or verified water levels, depending on availability.
    )
    AIR_TEMPERATURE = 'air_temperature'  # Air temperature as measured at the station.
    WATER_TEMPERATURE = 'water_temperature'  # Water temperature as measured at the station.
    WIND = 'wind'  # Wind speed, direction, and gusts as measured at the station.
    AIR_PRESSURE = 'air_pressure'  # Barometric pressure as measured at the station.
    AIR_GAP = 'air_gap'  # Air Gap (distance between a bridge and the water's surface) at the station.
    CONDUCTIVITY = 'conductivity'  # The water's conductivity as measured at the station.
    VISIBILITY = 'visibility'  # Visibility from the station's visibility sensor. A measure of atmospheric clarity.
    HUMIDITY = 'humidity'  # Relative humidity as measured at the station.
    SALINITY = 'salinity'  # Salinity and specific gravity data for the station.
    HOURLY_HEIGHT = 'hourly_height'  # Verified hourly height water level data for the station.
    HIGH_LOW = 'high_low'  # Verified high/low water level data for the station.
    DAILY_MEAN = 'daily_mean'  # Verified daily mean water level data for the station.
    MONTHLY_MEAN = 'monthly_mean'  # Verified monthly mean water level data for the station.
    ONE_MINUTE_WATER_LEVEL = (
        'one_minute_water_level'
        # One minute water level data for the station.
    )
    PREDICTIONS = 'predictions'  # 6 minute predictions water level data for the station.*
    DATUMS = 'datums'  # datums data for the stations.
    CURRENTS = 'currents'  # Currents data for currents stations.
    CURRENTS_PREDICTIONS = (
        'currents_predictions'
        # Currents predictions data for currents predictions stations.
    )


class COOPS_TidalDatum(Enum):
    CRD = 'CRD'  # Columbia River Datum
    IGLD = 'IGLD'  # International Great Lakes Datum
    LWD = 'LWD'  # Great Lakes Low Water Datum (Chart Datum)
    MHHW = 'MHHW'  # Mean Higher High Water
    MHW = 'MHW'  # Mean High Water
    MTL = 'MTL'  # Mean Tide Level
    MSL = 'MSL'  # Mean Sea Level
    MLW = 'MLW'  # Mean Low Water
    MLLW = 'MLLW'  # Mean Lower Low Water
    NAVD = 'NAVD'  # North American Vertical Datum
    STND = 'STND'  # Station Datum


class COOP_VelocityType(Enum):
    SPEED_DIR = 'speed_dir'  # Return results for speed and dirction
    DEFAULT = 'default'  # Return results for velocity major, mean flood direction and mean ebb dirction


class COOPS_Units(Enum):
    METRIC = 'metric'
    ENGLISH = 'english'


class COOPS_TimeZone(Enum):
    GMT = 'gmt'  # Greenwich Mean Time
    LST = 'lst'  # Local Standard Time. The time local to the requested station.
    LST_LDT = 'lst_ldt'  # Local Standard/Local Daylight Time. The time local to the requested station.


class COOPS_Interval(Enum):
    H = 'h'  # Hourly Met data and harmonic predictions will be returned
    HILO = 'hilo'  # High/Low tide predictions for all stations.


class COOPS_StationType(Enum):
    CURRENT = 'current'
    HISTORICAL = 'historical'


class COOPS_Station:
    def __init__(self, id: int):
        stations = coops_stations()
        if id not in stations.index:
            if id in stations['NWS ID'].values:
                id = stations.index[stations['NWS ID'] == id][0]
            else:
                raise ValueError(f'NWS id "{id}" not found')
        self.id = id

    @property
    @lru_cache(maxsize=1)
    def constituents(self) -> DataFrame:
        url = f'https://tidesandcurrents.noaa.gov/harcon.html?id={self.id}'
        response = requests.get(url)
        soup = BeautifulSoup(response.content, features='html.parser')
        table = soup.find_all('table', {'class': 'table table-striped'})[0]
        columns = [field.text for field in
                   table.find('thead').find('tr').find_all('th')]
        constituents = []
        for row in table.find_all('tr')[1:]:
            constituents.append([entry.text for entry in row.find_all('td')])
        constituents = DataFrame.from_records(constituents, columns=columns)
        constituents.rename(columns={'Constituent #': '#'}, inplace=True)
        constituents = constituents.astype(
                {'#': int, 'Amplitude': float, 'Phase': float, 'Speed': float}
        )
        constituents.set_index('#', inplace=True)
        return constituents

    def get(
            self,
            start_date: datetime,
            end_date: datetime = None,
            product: COOPS_Product = None,
            datum: COOPS_TidalDatum = None,
            units: COOPS_Units = None,
            time_zone: COOPS_TimeZone = None,
            interval: COOPS_Interval = None,
    ) -> DataFrame:
        query = COOPS_Query(
                station=self,
                start_date=start_date,
                end_date=end_date,
                product=product,
                datum=datum,
                units=units,
                time_zone=time_zone,
                interval=interval,
        )

        return query.data


class COOPS_Query:
    """
    interface with the NOAA Center for Operational Oceanographic Products and Services (CO-OPS) API
    https://api.tidesandcurrents.noaa.gov/api/prod/
    """

    URL = 'https://tidesandcurrents.noaa.gov/api/datagetter?'

    def __init__(
            self,
            station: COOPS_Station,
            start_date: datetime,
            end_date: datetime = None,
            product: COOPS_Product = None,
            datum: COOPS_TidalDatum = None,
            units: COOPS_Units = None,
            time_zone: COOPS_TimeZone = None,
            interval: COOPS_Interval = None,
    ):
        if isinstance(station, COOPS_Station):
            station = station.id
        if end_date is None:
            end_date = datetime.today()
        if product is None:
            product = COOPS_Product.WATER_LEVEL
        if datum is None:
            datum = COOPS_TidalDatum.MLLW
        if units is None:
            units = COOPS_Units.METRIC
        if time_zone is None:
            time_zone = COOPS_TimeZone.GMT
        if interval is None:
            interval = COOPS_Interval.H

        self.id = station
        self.start_date = start_date
        self.end_date = end_date
        self.product = product
        self.datum = datum
        self.units = units
        self.time_zone = time_zone
        self.interval = interval

        self.__previous_query = None

    @property
    def query(self):
        product = self.product
        if isinstance(product, Enum):
            product = product.value
        datum = self.datum
        if isinstance(datum, Enum):
            datum = datum.value
        units = self.units
        if isinstance(units, Enum):
            units = units.value
        time_zone = self.time_zone
        if isinstance(time_zone, Enum):
            time_zone = time_zone.value
        interval = self.interval
        if isinstance(interval, Enum):
            interval = interval.value

        return {
            'station': self.id,
            'begin_date': f'{self.start_date:%Y%m%d %H:%M}',
            'end_date': f'{self.end_date:%Y%m%d %H:%M}',
            'product': product,
            'datum': datum,
            'units': units,
            'time_zone': time_zone,
            'interval': interval,
            'format': 'json',
            'application': 'noaa/nos/csdl/stormevents',
        }

    @property
    def data(self) -> DataFrame:
        if self.__previous_query is None or self.query != self.__previous_query:
            response = requests.get(self.URL, params=self.query)
            data = DataFrame.from_records(
                    response.json()['data'], columns=['t', 'v', 's', 'f', 'q'],
            )
            data = data.astype({'v': float, 's': float})
            data['t'] = pandas.to_datetime(data['t'])
            self.__data = data
        return self.__data


@lru_cache(maxsize=1)
def __coops_stations_html_tables() -> bs4.element.ResultSet:
    response = requests.get(
            'https://access.co-ops.nos.noaa.gov/nwsproducts.html?type=current',
    )
    soup = BeautifulSoup(response.content, features='html.parser')
    return soup.find_all('div', {'class': 'table-responsive'})


@lru_cache(maxsize=1)
def coops_stations(station_type: COOPS_StationType = None) -> DataFrame:
    """
    retrieve a list of CO-OPS stations with associated metadata

    :param station_type: one of ``current`` or ``historical``
    :return: data frame of stations

    .. code-block:: python

        stations = coops_stations()

    """

    if station_type is None:
        return pandas.concat(
                [coops_stations(station_type) for station_type in
                 COOPS_StationType]
        )

    column_types = {'NOS ID': int, 'Latitude': float, 'Longitude': float}

    if station_type == COOPS_StationType.CURRENT:
        table_id = 'NWSTable'
        table_index = 0
    else:
        table_id = 'HistNWSTable'
        table_index = 1

    tables = __coops_stations_html_tables()

    stations_table = tables[table_index].find('table',
                                              {'id': table_id}).find_all('tr')

    stations_columns = [field.text for field in
                        stations_table[0].find_all('th')]
    stations = []
    for station in stations_table[1:]:
        stations.append(
                [value.text.strip() for value in station.find_all('td')])

    stations = DataFrame.from_records(stations, columns=stations_columns)
    stations = stations.astype(column_types)
    stations.set_index('NOS ID', inplace=True)

    if station_type == COOPS_StationType.HISTORICAL:
        stations['Removed Date/Time'] = pandas.to_datetime(
                stations['Removed Date/Time'])

    return stations


def coops_stations_within_region(
        region: Polygon,
        station_type: COOPS_StationType = None,
) -> ['COOPS_Station']:
    """
    retrieve all stations within the specified region of interest

    :param region: polygon or multipolygon denoting region of interest
    :param station_type: one of ``current`` or ``historical``
    :return: data frame of stations within the specified region

    .. code-block:: python

        from shapely.geometry import Polygon

        polygon = Polygon(...)

        stations = coops_stations_within_region(region=polygon)

    """

    all_stations = coops_stations(station_type)
    points = [Point(*row) for row in all_stations[['Longitude', 'Latitude']]]

    return [
        COOPS_Station(id=all_stations.iloc[index]['NOS ID'])
        for index, point in enumerate(points) if point.within(region)
    ]


def coops_data_within_region(
        region: Union[Polygon, MultiPolygon],
        start_date: datetime,
        end_date: datetime = None,
        product: COOPS_Product = None,
        datum: COOPS_TidalDatum = None,
        units: COOPS_Units = None,
        time_zone: COOPS_TimeZone = None,
        interval: COOPS_Interval = None,
):
    """
    retrieve CO-OPS data from within the specified region of interest

    :param region: polygon or multipolygon denoting region of interest
    :param start_date: start date of CO-OPS query
    :param end_date: start date of CO-OPS query
    :param product: CO-OPS product
    :param datum: tidal datum
    :param units: one of ``metric`` or ``english``
    :param time_zone: station time zone
    :param interval: data time interval
    :return: data frame of data within the specified region

    .. code-block:: python

        from datetime import datetime, timedelta

        from shapely.geometry import MultiPolygon

        polygon = MultiPolygon(...)

        coops_data_within_region(region=polygon, start_date=datetime.now() - timedelta(days=2), end_date=datetime.now())

    """

    stations = coops_stations_within_region(region=region)
    return pandas.concat(
            [
                station.get(
                        start_date=start_date,
                        end_date=end_date,
                        product=product,
                        datum=datum,
                        units=units,
                        time_zone=time_zone,
                        interval=interval,
                )
                for station in stations
            ]
    )
