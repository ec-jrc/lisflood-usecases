import datetime
import functools
import glob
import os
import subprocess
import warnings
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Union

import altair as alt
import ipyleaflet
import ipywidgets
import matplotlib.pyplot as plt
import netCDF4
import numpy as np
import pandas as pd
import xarray as xr
import cartopy.crs as ccrs
import cartopy.io.img_tiles as cimgt
from ipyfilechooser import FileChooser
from IPython.display import display
from matplotlib import rc

from docs.lisflood_read_plot import read_tss

# dictionary with editable calibration parameters including allowed data range
parameter = {
    "SnowMeltCoef": {
        "label": "Snow melt coefficient",
        "min": 2.5, "max": 6.5, "step": 0.01, "format": ".2f", "units": "[mm/°C day]"
    },
    "b_Xinanjiang": {
        "label": "Xinanjiang power parameter",
        "min": 0.5, "max": 5, "step": 0.01, "format": ".2f", "units": "[-]"
    },
    "PowerPrefFlow": {
        "label": "Preferential flow",
        "min": 0.5, "max": 8, "step": 0.01, "format": ".2f", "units": "[-]"
    },
    "GwPercValue": {
        "label": "Groundwater percolation",
        "min": 0.01, "max": 2, "step": 0.01, "format": ".2f", "units": "[-]"
    },
    "UpperZoneTimeConstant": {
        "label": "Upper groundwater zone constant",
        "min": 0.01, "max": 40, "step": 0.01, "format": ".2f", "units": "[days]"
    },
    "LowerZoneTimeConstant": {
        "label": "Lower groundwater zone constant",
        "min": 1000, "max": 10500, "step": 5, "format": ".0f", "units": "[days]"
    },
    "GwLoss": {
        "label": "Groundwater loss",
        "min": 0, "max": 0.5, "step": 0.01, "format": ".2f", "units": "[mm/day]"
    },
    "CalChanMan": {
        "label": "Main channel roughness (factor of Manning's n)",
        "min": 0.1, "max": 20, "step": 0.01, "format": ".2f", "units": "[-]"
    },
    "CalChanMan2": {
        "label": "Floodplain roughness (factor of Manning's n)",
        "min": 0.1, "max": 20, "step": 0.01, "format": ".2f", "units": "[-]"
    },
}

# Map internal names to display names for clarity
optional_modules = {
    'Initialization': {
        'InitLisflood': 'Initialize LISFLOOD',
        'InitLisfloodwithoutSplit': 'Initialize without split',
    },
    'Routing': {
        'SplitRouting': 'Split routing',
        'inflow': 'External inflow',
    },
    'Water bodies': {
        'simulateReservoirs': 'Simulate reservoirs',
        'simulateLakes': 'Simulate lakes',
        'openwaterevapo': 'Evaporation from open water',
    },
    'Groundwater': {
        'groundwaterSmooth': 'Groundwater smoothing',
    },
    'Irrigation': {
        'riceIrrigation': 'Rice irrigation',
        'drainedIrrigation': 'Drained irrigation',
    },
    'Water use': {
        'wateruse': 'Water use',
        'useWaterDemandAveYear': 'Use average water demand',
        'TransientWaterDemandChange': 'Use transient water demand',
        'wateruseRegion': 'Water use region',
        'indicator': 'Compute indicators',
    },
    'Input-output': {
        'readNetcdfStack': 'Read NetCDF stack',
        'writeNetcdf': 'Write NetCDF',
        'writeNetcdfStack': 'Write NetCDF stack'
    },
}

# Helper function to create module checkboxes
def _create_module_tab(root):
    """
    Parses XML and creates module checkbox widgets, organized by group,
    using a single source of truth.
    """
    global optional_modules_xml
    global module_checkboxes

    module_checkboxes = {}
    optional_modules_xml = [root[i].find("./lfoptions") for i in range(2)]

    # First, create all the checkboxes and store them in the global dictionary
    for element in optional_modules_xml[1]:
        module_name = element.attrib['name']
        display_name = next((v for group in optional_modules.values() for k, v in group.items() if k == module_name), module_name)
        module_checkboxes[module_name] = ipywidgets.Checkbox(
            value=bool(int(element.attrib['choice'])),
            description=display_name,
            disabled=False,
            style={'description_width': 'initial'}
        )

    # Now, use the checkboxes to build the grouped VBoxes
    grouped_vboxes = []
    for group_title, group_modules in optional_modules.items():
        vbox_content = [ipywidgets.HTML(value=f'<b>{group_title}:</b>')]
        for module_name in group_modules:
            if module_name in module_checkboxes:
                vbox_content.append(module_checkboxes[module_name])
        grouped_vboxes.append(ipywidgets.VBox(vbox_content))

    return grouped_vboxes

# Helper function to create the date picker widgets
def _create_date_tab(root):
    """Parses XML dates and creates date picker widgets."""
    global StepStart
    global StepEnd
    
    common_widget_style = {
        'layout': ipywidgets.Layout(width='40%'), 
        'style': {'description_width': '25ex'}
    }

    StepStart = [root[i].find("./lfuser/group/textvar[@name='StepStart']") for i in range(2)]
    StepStart_iso = [datetime.datetime.strptime(s.attrib['value'].split()[0], '%d/%m/%Y').strftime('%Y-%m-%d')
                      for s in StepStart]

    StepEnd = [root[i].find("./lfuser/group/textvar[@name='StepEnd']") for i in range(2)]
    StepEnd_iso = [datetime.datetime.strptime(e.attrib['value'].split()[0], '%d/%m/%Y').strftime('%Y-%m-%d')
                    for e in StepEnd]
    
    StepStart_picker = [
        ipywidgets.DatePicker(
            description='{0:>7} | {1:<10}'.format('Pre-run', 'Start date'),
            value=datetime.date.fromisoformat(StepStart_iso[0]),
            **common_widget_style
        ),
        ipywidgets.DatePicker(
            description='{0:>7} | {1:<10}'.format('Run', 'Start date'),
            value=datetime.date.fromisoformat(StepStart_iso[1]),
            **common_widget_style
        )
    ]
    
    StepEnd_picker = [
        ipywidgets.DatePicker(
            description='{0:>7} | {1:<10}'.format('Pre-run', 'End date'),
            value=datetime.date.fromisoformat(StepEnd_iso[0]),
            **common_widget_style
        ),
        ipywidgets.DatePicker(
            description='{0:>7} | {1:<10}'.format('Run', 'End date'),
            value=datetime.date.fromisoformat(StepEnd_iso[1]),
            **common_widget_style
        )
    ]
    return StepStart_picker, StepEnd_picker

# Helper function to create the output grids
def _create_output_tab(module_checkboxes):
    """Creates the grid layout for output checkboxes."""
    # Define a dictionary for a cleaner way to group outputs
    output_groups = {
        'Surface water': {
            'repDischargeMaps': 'Discharge maps', 
            'repDischargeTs': 'Discharge time series', 
            'repSurfaceRunoffMaps': 'Surface runoff maps',
            'repSnowCoverMaps': 'Snow cover maps', 
            'repSnowMeltMaps': 'Snow melt maps',
            'repsimulateReservoirs': 'Reservoir simulation',
            'repsimulateLakes': 'Lake simulation', 
        },
        'Soil': {
            'repThetaMaps': 'Soil moisture maps',
            'repThetaForestMaps': 'Soil moisture maps in forests', 
            'repThetaIrrigationMaps': 'Soil moisture maps in irrigated areas',
        },
        'Groundwater': {
            'repPFMaps': 'Matric potential maps',
            'repPFForestMaps': 'Matric potential maps in forests',
            'repUZMaps': 'Upper groundwater zone maps',
            'repLZMaps': 'Lower groundwater zone maps',
        },
        'Water use': {
            'repTotalAbs': 'Total abstraction',
            'repTotalWUse': 'Total water use',
        },
        'State and end maps': {
            'repStateMaps': 'Multiple time steps', 
            'repEndMaps': 'Final time step',
        }
    }

    output_grid = ipywidgets.GridspecLayout(20, 3, height='auto')
    
    all_groups = list(output_groups.items())
    num_groups = len(all_groups)
    num_cols = 3
    
    # Calculate how many groups go in each column
    group_per_col = (num_groups + num_cols - 1) // num_cols
    
    for i in range(num_cols):
        vbox_list = []
        # Get the groups for the current column
        start_index = i * group_per_col
        end_index = min((i + 1) * group_per_col, num_groups)
        
        for j in range(start_index, end_index):
            group_title, group_modules = all_groups[j]
            # VBox to hold the group title and its checkboxes
            vbox_content = [ipywidgets.HTML(value=f'<b>{group_title}:</b>')] + \
                           [ipywidgets.Checkbox(value=False, description=display_name, style={'description_width': '0ex'}) for display_name in group_modules.values()]
            vbox_list.append(ipywidgets.VBox(vbox_content))
            
        # Place the combined VBox for this column into the grid
        output_grid[:, i] = ipywidgets.VBox(vbox_list)

    return output_grid

# Helper function to create calibration sliders
def _create_parameter_tab(root):
    """Parses XML and creates calibration slider widgets."""
    global parameter_xml
    global parameter_sliders

    parameter_sliders = {}
    parameter_xml = [root[i].find("./lfuser") for i in range(2)]
    if parameter_xml[1] is None:
        print("Error: Could not find lfuser group in the RUN settings file.")
        return {}

    # Iterate through the desired order to create the sliders
    for param_name, specs in parameter.items():
        element = parameter_xml[1].find(f".//textvar[@name='{param_name}']")
        if element is not None:
            slider_widget = ipywidgets.HBox([
                ipywidgets.FloatSlider(
                    value=float(element.attrib['value']),
                    min=specs['min'],
                    max=specs['max'],
                    step=specs['step'],
                    description=specs['label'],
                    disabled=False,
                    continuous_update=False,
                    orientation='horizontal',
                    readout=True,
                    readout_format=specs['format'],
                    layout=ipywidgets.Layout(width='60%'),
                    style={'description_width': '50ex'}
                    ),
                ipywidgets.Label(value=specs['units'])
            ])
            parameter_sliders[param_name] = slider_widget
            
    return parameter_sliders

# Helper function to create the map
def _create_map(root, module_checkboxes):
    """Initializes and configures the ipyleaflet map widget."""
    global m
    global marker
    global coordinates

    coordinates = [root[i].findall("./lfuser/group/textvar/[@name='Gauges']")[0] for i in range(2)]
    lon, lat = coordinates[1].attrib['value'].split()
    center = (float(lat), float(lon))
    m = ipyleaflet.Map(zoom=10, center=center, scroll_wheel_zoom=True)
    marker = ipyleaflet.Marker(location=center, draggable=True)
    m.add_layer(marker)
    m.layout.display = "block" if module_checkboxes['repDischargeTs'].value else "none"
    return m, marker

# Helper function to link widget observers
def _link_observers(module_checkboxes, m):
    """Sets up the observer links for widget interactions."""
    module_checkboxes['SplitRouting'].observe(on_split_routing_clicked, names='value')
    module_checkboxes['repDischargeTs'].observe(on_rep_discharge_ts_clicked, names='value')

# Main function to show settings
def show_settings(chooser, settings_files):
    """
    Reads XML settings, creates and displays an interactive UI
    for configuring a LISFLOOD simulation.
    """
    if settings_files[0].selected is None or settings_files[1].selected is None:
        return

    global tree
    global CalendarDayStart
    global DtSec_xml
    global DtSec_box
    global optional_modules_xml
    global parameter_xml
    global parameter_sliders
    global module_checkboxes
    global m
    global marker
    global coordinates
    global StepStart_picker
    global StepEnd_picker

    # Create output folder if it does not exist
    out_dir = Path(settings_files[1].selected_path) / "results"
    out_dir.mkdir(parents=True, exist_ok=True)

    # opens settings file of PRE-RUN ([0]) and RUN ([1]) in list
    tree = [ET.parse(f.selected) for f in settings_files]
    root = [t.getroot() for t in tree]

    # gets timestep
    DtSec_xml = [root[i].find("./lfuser/group/textvar[@name='DtSec']") for i in range(2)]
    if DtSec_xml[0] is None:
        print("Error: Could not find 'DtSec' in the PRE-RUN settings file. Please check the file and the XML path.")
        return 
    DtSec_box = ipywidgets.BoundedIntText(
        value=DtSec_xml[0].attrib['value'],
        min=1,
        max=31536000,
        step=60,
        description='Timestep [s]:',
        layout=ipywidgets.Layout(width='40%'),
        style={'description_width': '25ex'}
        )

    # gets calendar day start
    calendar_day_start_element = root[1].find("./lfuser/group/textvar[@name='CalendarDayStart']")
    if calendar_day_start_element is None:
        print("Error: Could not find 'CalendarDayStart' in the RUN settings file. Please check the file and the XML path.")
        return
    date_time_str = calendar_day_start_element.attrib['value']
    CalendarDayStart = datetime.datetime.strptime(date_time_str, '%d/%m/%Y %H:%M')

    # Create UI widgets
    grouped_module_vboxes = _create_module_tab(root)
    StepStart_picker, StepEnd_picker = _create_date_tab(root)
    output_grid = _create_output_tab(module_checkboxes)
    parameter_sliders = _create_parameter_tab(root)
    m, marker = _create_map(root, module_checkboxes)

    # Organize grouped module vboxes into a single GridBox
    optional_modules_grid = ipywidgets.GridBox(
        grouped_module_vboxes,
        layout=ipywidgets.Layout(grid_template_columns="repeat(2, 1fr) 1fr")
    )

    # Define UI layout and tabs
    tabs = ipywidgets.Tab()
    tabs.children = [
        ipywidgets.VBox([optional_modules_grid]),
        ipywidgets.VBox([StepStart_picker[0], StepEnd_picker[0], StepStart_picker[1], StepEnd_picker[1], DtSec_box]),
        ipywidgets.VBox(list(parameter_sliders.values())),
        ipywidgets.VBox([output_grid, m]),
    ]
    
    # Set the titles for the tabs in the new order
    tabs.set_title(0, 'Optional modules')
    tabs.set_title(1, 'Simulation period')
    tabs.set_title(2, 'Model parameters')
    tabs.set_title(3, 'Outputs')

    # Link widget observers
    _link_observers(module_checkboxes, m)

    # Display UI
    display(tabs)
    
    # Create an output area for logging
    output_area = ipywidgets.Output()

    # Button to start processing method
    processing_button = ipywidgets.Button(description="Start")
    processing_button.on_click(
        functools.partial(
            on_processing_button_clicked, 
            settings_files=settings_files, 
            output_area=output_area
        )
    )
    display(processing_button)

# callback function to write input data to XML files and start processing
# callback function to write input data to XML files and start processing
def on_processing_button_clicked(b, settings_files, output_area):
    """
    Updates XML settings filºes with user input and executes the LISFLOOD simulation.
    """
    # Clear previous output before each run
    output_area.clear_output()

    with output_area:
        print("Starting LISFLOOD processing...")

        global datasets
        global parameter_xml
        global parameter_sliders
        global optional_modules_xml
        global module_checkboxes
        global tree
        global StepStart
        global StepEnd
        global DtSec_xml
        global DtSec_box
        global coordinates
        global marker
        global StepStart_picker
        global StepEnd_picker

        # Check if 'datasets' exists and close any open NetCDF files
        print("Checking for previous datasets...")
        if 'datasets' in globals():
            for _, dataset in datasets:
                dataset.close()
            datasets.clear()
            print("Closed and cleared previous datasets.")
        else:
            datasets = []
            print("No previous datasets found.")
        
        # Update calibration parameter values in XML from sliders
        print("\nUpdating calibration parameters...")
        for root_xml in parameter_xml:
            # Find all 'textvar' elements within the 'lfuser' group
            textvar_elements = root_xml.findall(".//textvar")
            for element in textvar_elements:
                param_name = element.attrib['name']
                if param_name in parameter:
                    new_value = str(parameter_sliders[param_name].children[0].value)
                    element.attrib['value'] = new_value
                    print(f"  - Parameter '{param_name}' set to value '{new_value}'")


        # Update optional module choices in XML from checkboxes
        print("\nUpdating optional modules...")
        for root_xml in optional_modules_xml:
            for element in root_xml:
                if element.tag == 'setoption':
                    module_name = element.attrib['name']
                    new_choice = str(int(module_checkboxes[module_name].value))
                    element.attrib['choice'] = new_choice
                    print(f"  - Module '{module_name}' choice set to '{new_choice}'")

        # Configure SplitRouting and InitLisflood options in both XML files
        split_routing = module_checkboxes['SplitRouting'].value
        print(f"\nConfiguring routing options (SplitRouting is {'enabled' if split_routing else 'disabled'})...")
        for i, root_xml in enumerate(optional_modules_xml):  
            # Determine and set the correct InitLisflood choice based on split_routing
            init_lisflood_choice = str(int(split_routing and (i == 0)))
            init_lisflood_without_split_choice = str(int(not split_routing and (i == 0)))

            root_xml.findall("setoption[@name='SplitRouting']")[0].attrib['choice'] = str(int(split_routing))
            root_xml.findall("setoption[@name='InitLisflood']")[0].attrib['choice'] = init_lisflood_choice
            root_xml.findall("setoption[@name='InitLisfloodwithoutSplit']")[0].attrib['choice'] = init_lisflood_without_split_choice
            print(f"  - File {i+1}: InitLisflood set to '{init_lisflood_choice}', InitLisfloodwithoutSplit set to '{init_lisflood_without_split_choice}'")

        # Write simulation dates, timestep, and coordinates to both XML files
        print("\nUpdating simulation dates, timestep, and coordinates...")
        for i in range(len(tree)):
            date_format_in = "%Y-%m-%d"
            date_format_out = '%d/%m/%Y'
            
            start_date_str = str(StepStart_picker[i].value)
            start_date_formatted = datetime.datetime.strptime(start_date_str, date_format_in).strftime(date_format_out)
            StepStart[i].attrib['value'] = f"{start_date_formatted} {StepStart[i].attrib['value'].split()[1]}"

            end_date_str = str(StepEnd_picker[i].value)
            end_date_formatted = datetime.datetime.strptime(end_date_str, date_format_in).strftime(date_format_out)
            StepEnd[i].attrib['value'] = f"{end_date_formatted} {StepEnd[i].attrib['value'].split()[1]}"

            DtSec_xml[i].attrib['value'] = str(DtSec_box.value)

            if module_checkboxes['repDischargeTs'].value:
                coordinates[i].attrib['value'] = f"{marker.location[1]} {marker.location[0]}"
            
            print(f"  - Writing updated settings to {settings_files[i].selected}...")
            tree[i].write(settings_files[i].selected)
            print(f"  - Successfully wrote settings to {settings_files[i].selected}.")

        # Execute LISFLOOD pre-run and run
        print('\n--- LISFLOOD PRE-RUN ---')
        try:
            result = subprocess.run(['lisflood', settings_files[0].selected], check=True, capture_output=True, text=True)
            print("PRE-RUN completed successfully.")
            if result.stdout:
                print("LISFLOOD stdout:")
                print(result.stdout)
        except subprocess.CalledProcessError as e:
            print(f"Error running LISFLOOD PRE-RUN:\n{e.stderr}")
            return
            
        print('\n--- LISFLOOD RUN ---')
        try:
            result = subprocess.run(['lisflood', settings_files[1].selected], check=True, capture_output=True, text=True)
            print("RUN completed successfully.")
            if result.stdout:
                print("LISFLOOD stdout:")
                print(result.stdout)
        except subprocess.CalledProcessError as e:
            print(f"Error running LISFLOOD RUN:\n{e.stderr}")
            return
            
        print("\nProcessing complete.")

# Callback function to change map visibility
def on_rep_discharge_ts_clicked(change):
    """
    Toggles the visibility of the interactive map based on the
    state of the 'repDischargeTs' checkbox.
    """
    global m

    m.layout.display = "block" if change['new'] else "none"

# Callback function to prevent false input regarding SplitRouting
def on_split_routing_clicked(change):
    """
    Ensures a valid combination of InitLisflood and InitLisfloodwithoutSplit
    checkboxes based on the state of the SplitRouting checkbox.
    """
    global module_checkboxes
    
    if change['new']:
        module_checkboxes['InitLisflood'].disabled = False
        module_checkboxes['InitLisfloodwithoutSplit'].value = False
        module_checkboxes['InitLisfloodwithoutSplit'].disabled = True
    else:
        module_checkboxes['InitLisflood'].value = False
        module_checkboxes['InitLisflood'].disabled = True
        module_checkboxes['InitLisfloodwithoutSplit'].value = True

# updates date of spatial plot from time slider
def _update_time(date):
    """
    Callback function to update the map based on the selected date.   
    """
    global datasets
    global datevar
    global im
    global variable_dropdown
    
    variable = variable_dropdown.value
    im.set_array(datasets[variable].isel(time=date).data.ravel())
    plt.title(
        f'{variable}: {pd.to_datetime(datevar[date]).strftime("%d %b %Y")}',
        size='xx-large'
        )
    plt.draw()

#  updates parameter of spatial plot from dropdown menu
def _update_variable(variable):
    """
    Callback function to update the map based on the selected variable.
    """
    global datasets
    global datevar
    global im
    global cbar
    global date_slider
    
    new_data_array = datasets[variable]
    
    # Update the array data
    im.set_array(new_data_array.isel(time=date_slider.value).data.ravel())
    
    # Update the color normalization based on the full range of the new variable
    im.set_clim(vmin=new_data_array.min().item(), vmax=new_data_array.max().item())
    
    # Update the color bar's label
    cbar.set_label(new_data_array.attrs["units"], fontsize=12)
    cbar.update_normal(im)
    
    title = '{}: {}'.format(variable, datevar[date_slider.value].strftime('%d %b %Y'))
    plt.title(title, size='xx-large')
    plt.draw()

# plots spatial and time series output data
def plot_results(
        chooser, 
        output_dir: Optional[Union[str, Path]] = None
):
    """
    Plot results of the LISFLOOD simulation.
    """
    # sets path to output directory depending on function parameters
    if output_dir:
        path_results = Path(chooser.selected_path)
        settings_file = next(path_results.parent.glob('*Run.xml'))
    else:
        path_model = Path(chooser.selected_path)
        path_results = path_model / 'results'
        settings_file = path_model / chooser.selected_filename

    # checks whether output data exists
    if not (any(path_results.glob('*.nc')) and any(path_results.glob('*.tss'))):
        print(f'No output files in {path_results}.')
        return

    global datevar

    # discharge time series
    tss_file = path_results / 'dis_run.tss'
    if tss_file.is_file():
        # read
        df = read_tss(
            tss=tss_file, 
            xml=settings_file,
            squeeze=False
        )
        df.columns = ['value']
        df.index.name = 'date'
        df.reset_index(inplace=True)
        df['setting'] = 'discharge'

        # plot
        selection = alt.selection_point(fields=['setting'], bind='legend')
        chart = alt.Chart(df
                ).mark_line(point=True
                ).encode(x='date:T',
                        y='value:Q',
                        color=alt.Color('setting', legend=alt.Legend(title="Variable")),
                        opacity=alt.condition(selection, alt.value(1), alt.value(0.2))
                ).add_params(selection
                ).interactive(bind_y=False
                ).properties(width=800, height=300)
        # display outputs
        display(ipywidgets.HTML(value = f"<left><b><font size=5>{'Discharge Time Series'}</b></left>"))
        display(chart)

    # output maps
    nc_files = nc_files = [file for file in path_results.glob('*.nc') if file.stem not in ['lzavin', 'avgdis']]
    if len(nc_files) == 0:
        print(f'No NetCDF files in the results folder: {path_results}.')
        return

    global datasets
    global date_slider
    global variable_dropdown
    global im
    global cbar 

    if 'datasets' in locals():
        datasets.clear()
    else:
        datasets = []

    # read maps
    datasets = {file.stem: xr.open_dataarray(file) for file in nc_files}

    # get dates from the datasets
    first_key = next(iter(datasets))
    datevar = datasets[first_key]['time'].data

    # create drowdown menu with all available outputs
    variable_dropdown = ipywidgets.Dropdown(
        options=list(datasets), 
        description='Variable:'
    )
    # create date slider for given time period
    date_slider = ipywidgets.IntSlider(
        min=0, 
        max=len(datevar) - 1, 
        step=1, 
        value=0,
        description='Date:'
    )
    # create simulation controls
    play = ipywidgets.Play(
        min=0,
        max=len(datevar) - 1,
        step=1,
        description="Press play",
        disabled=False
    )

    # plot the map
    out_spatial = ipywidgets.Output()
    with out_spatial:
        # extract data array
        variable = variable_dropdown.value
        da = datasets[variable]

        # Create a figure and axes with a Plate Carree projection.
        fig, ax = plt.subplots(
            figsize=(10, 6),
            subplot_kw={'projection': ccrs.PlateCarree()}
        )

        # Set the extent of the map based on the data's geographical bounds.
        buffer = 0.5
        extent = [
                da.lon.min().item() - buffer,
                da.lon.max().item() + buffer,
                da.lat.min().item() - buffer,
                da.lat.max().item() + buffer
        ]
        ax.set_extent(extent, crs=ccrs.PlateCarree())

        # Add the map image tiles for geographical context.
        request = cimgt.OSM()
        ax.add_image(request, 6)
    
        # Add geographical features to provide more context.
        ax.coastlines(resolution='50m', color='black', linewidth=1)
        ax.gridlines(draw_labels=True, linestyle='--', color='gray', alpha=0.5)

        # Plot the data.
        im = ax.pcolormesh(
            da.lon,
            da.lat,
            da.isel(time=0).data,
            vmin=da.min().item(),
            vmax=da.max().item(),
            cmap=plt.cm.viridis_r,
            alpha=0.6,
            transform=ccrs.PlateCarree(),
        )

        # Add the color bar and set its label and font size.
        cbar = plt.colorbar(im, shrink=0.5, pad=0.1)
        cbar.set_label(da.attrs["units"], fontsize=12)
        cbar.ax.tick_params(labelsize=12)

        _update_time(0)

    # update variable, time or when a simulation is started
    ipywidgets.interactive(_update_variable, variable=variable_dropdown)
    ipywidgets.interactive(_update_time, date=date_slider)
    ipywidgets.jslink((play, 'value'), (date_slider, 'value'))

    # display outputs
    display(ipywidgets.HTML(value = f"<left><b><font size=5>{'Spatial Outputs'}</b></left>"))
    display(out_spatial)
    display(ipywidgets.HBox([play, date_slider, variable_dropdown]))