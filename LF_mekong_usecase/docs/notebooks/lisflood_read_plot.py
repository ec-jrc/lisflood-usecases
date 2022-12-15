import numpy as np
import pandas as pd
import xml.etree.ElementTree as ET
from dateutil import parser
from datetime import datetime, timedelta
import xarray as xr
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec


def xml_timeinfo(xml):
    """It extracts the temporal information from the settings XML file.
    
    Input:
    ------
    xml:               str. A XML settings file (path, filename and extension)
    
    Output:
    -------
    CalendarDayStart:  datetime. Origin of time considered in the simulation
    DtSec:             int. Temporal resolution of the simulation in seconds
    StepStart:         datetime. First timestep of the simulation
    StepEnd:           datetime. Last timestep of the simulation
    """
    
    # extract temporal info from the XML
    tree = ET.parse(xml)
    root = tree.getroot()
    CalendarDayStart = root.find('.//textvar[@name="CalendarDayStart"]').attrib['value']
    CalendarDayStart = parser.parse(CalendarDayStart, dayfirst=True)
    DtSec = int(root.find('.//textvar[@name="DtSec"]').attrib['value'])
    StepStart = root.find('.//textvar[@name="StepStart"]').attrib['value']
    try:
        StepStart = CalendarDayStart + int(StepStart) * timedelta(seconds=DtSec)
    except:
        StepStart = parser.parse(StepStart, dayfirst=True)
    StepEnd = root.find('.//textvar[@name="StepEnd"]').attrib['value']
    try:
        StepEnd = CalendarDayStart + int(StepEnd) * timedelta(seconds=DtSec)
    except:
        StepEnd = parser.parse(StepEnd, dayfirst=True)
        
    return CalendarDayStart, DtSec, StepStart, StepEnd


def read_tss(tss, xml=None, squeeze=True):
    """It generates a Pandas DataFrame or Series from a TSS file. The settings XML file is required to add the temporal information to the time series; if not provided, the index will contain integers indicating the timestep since the considered origin of time.
    
    Inputs:
    -------
    tss:     str. The TSS file (path, filename and extension) to be read.
    xml:     str. The XML settings file (path, filename and extension) for the simulation that created the TSS file.
    squeeze: boolean. If the TSS file has only one timeseries, if converts the pandas.DataFrame into a pandas.Series
    
    Output:
    -------
    df:      pandas.DataFrame or pandas.Series. 
    """
 
    # extract info from the header
    with open(tss, mode='r') as f:
        header = f.readline()
        n_cols = int(f.readline().strip())
        cols = [f.readline().strip() for i in range(n_cols)]        
    
    # extract timeseries
    df = pd.read_csv(tss, skiprows=2 + n_cols, delim_whitespace=True, header=None)
    df.columns = cols
    
    # define timesteps
    if xml is None:
        df.set_index(cols[0], drop=True, inplace=True)
    else:
        df.drop(cols[0], axis=1, inplace=True)
        # extract temporal info from the XML
        CalendarDayStart, DtSec, StepStart, StepEnd = xml_timeinfo(xml)
        # generate timesteps
        df.index = pd.date_range(start=StepStart, end=StepEnd, freq=f'{DtSec}s')
        #df.index.name = 'timesteps'

    if squeeze & (df.shape[1] == 1):
        df = df.iloc[:,0]
        
    return df


def plot_map_timeseries(dataarray, agg='mean', **kwargs):
    """It creates a plot that shows a map of the temporal aggregation of the DataArray and a timeseries of its spatial aggregation
    
    Inputs:
    -------
    dataarray:   xarray.DataArray. 3D array with the data to be plotted
    agg:         string. Aggregation function to be used: either 'mean' or 'sum'
    
    Output:
    -------
    The plot
    """
    
    fig = plt.figure(figsize=kwargs.get('figsize', (12, 4)))
    gs = GridSpec(1, 3, figure=fig)

    # map of daily mean
    ax1 = fig.add_subplot(gs[0,0])
    if agg == 'mean':
        da_agg = dataarray.mean('time')
    elif agg == 'sum':
        da_agg = dataarray.sum('time')
    da_agg.plot(ax=ax1, cmap=kwargs.get('cmap', 'viridis'),
                cbar_kwargs={'label': kwargs.get('label', dataarray.name),
                             "orientation": "horizontal",
                             "shrink": 0.8,
                             "aspect": 40,
                             "pad": 0.1});
    ax1.axis('off');

    # daily timeseries of areal mean
    ax2 = fig.add_subplot(gs[0,1:])
    dataarray.mean(['lat', 'lon']).plot(lw=kwargs.get('lw', 1), ax=ax2, color=kwargs.get('color', 'C0'))
    if 'label' in kwargs:
        ax2.set_ylabel(kwargs['label'])
    if 'xlim' in kwargs:
        ax2.set_xlim(kwargs['xlim'])
    if 'ylim' in kwargs:
        ax2.set_ylim(kwargs['ylim'])
    
    
def plot_reservoir(df, clim=None, nlim=None, flim=None, **kwargs):
    """It generates a plot with the results of the reservoir simulation
    
    Inputs:
    -------
    df:    pandas.DataFrame (n_timesteps, 3). Timeseries simulated by LISFLOOD. It must contain three columns: inflo, outflow and filling
    clim:  float. Conservative limit on the reservoir's relative filling
    nlim:  float. Normal limit on the reservoir's relative filling
    flim:  float. Flood limit on the reservoir's relative filling
    
    Output:
    -------
    A lineplot representing inflow, outflow and relative filling of the reservoir
    """
    
    fig, ax = plt.subplots(figsize=kwargs.get('figsize', (16, 4)))
    
    # plot flow timeseries
    for var in ['inflow', 'outflow']:
        ax.plot(df[var], lw=1, label=var)
    xmin, xmax = df.index.min(), df.index.max()
    ax.set(ylim=(0, 5000), xlim=(xmin, xmax))
    ax.set_ylabel('flow (m3/s)')
    
    # plot relative filling
    ax2 = ax.twinx()
    ax2.fill_between(df.index, df.filling, color='gray', alpha=.1, zorder=0, label='filling')
    if clim is not None:
        ax2.hlines(clim, xmin, xmax, 'k', ls=':', lw=.5, label='conservative fil.')
    if clim is not None:
        ax2.hlines(nlim, xmin, xmax, 'k', ls='--', lw=.5, label='normal fil.')
    if clim is not None:
        ax2.hlines(flim, xmin, xmax, 'k', ls='-', lw=.5, label='flood fil.')
    ax2.set(ylim=(0, 1))
    ax2.set_ylabel('relative filling (-)')
    
    fig.legend(ncol=2, bbox_to_anchor=[1.025, .8, .1, .1]);
    
    
    
def plot_mapstacks(dct, agg='mean', **kwargs):
    """It creates a combined plot of maps and time series. In the top row of the graph, it plots the mean over time map for each of the map stacks provided. In the bottom row of the graph, it plots a lineplot with the spatial mean timeseries of each of the mapstacks.
    
    Inputs:
    -------
    dct:   dictionary of dataarray. A dictionary containing as many map stacks (loaded as xarray.dataarray) as wanted.
    agg:   string. Aggregation function to be used: either 'mean' (default) or 'sum'
    
    Output:
    -------
    A plot that shows spatial variability (maps of mean over time) and temporal variability (lineplot of mean over space) for each of the provided maps
    """

    # configure plot
    nrows = kwargs.get('nrows', 1)
    ncols = int(np.ceil(len(dct) / nrows))

    fig = plt.figure(figsize=kwargs.get('figsize', (5 * ncols, 8 * nrows)))
    gs = GridSpec(1 + nrows, ncols, figure=fig)
    ax_ts = fig.add_subplot(gs[-1,:])
    cmaps = ['Blues', 'Greens', 'Reds', 'Purples', 'Oranges', 'Greys']
    colors = ['royalblue', 'forestgreen', 'firebrick', 'purple', 'orange', 'grey']

    # plot
    for i, (var, da) in enumerate(dct.items()):
        # map
        r, c = int(i / ncols), i % ncols
        ax = fig.add_subplot(gs[r,c])
        da.mean('time').plot(ax=ax, cmap=cmaps[i], vmin=kwargs.get('vmin', None), vmax=kwargs.get('vmax', None))
        ax.axis('off')
        

        # timeserie
        if agg == 'mean':
            da.mean(['lat', 'lon']).plot(ax=ax_ts, color=colors[i], lw=.7, label=var)
        elif agg == 'sum':
            da.sum(['lat', 'lon']).plot(ax=ax_ts, color=colors[i], lw=.7, label=var)
    
    # configure timeseries plot
    if 'ylim' in kwargs:
        ax_ts.set_ylim(kwargs['ylim'])
    ax_ts.set(xlim=(da.time.data[0], da.time.data[-1]),
              ylabel='{0} [{1}]'.format(kwargs.get('ylabel', ''), da.units),
              yscale=kwargs.get('yscale', 'linear'))
    ax_ts.legend(loc=8, ncol=len(dct), bbox_to_anchor=[0.25, -.4, .5, .1]);