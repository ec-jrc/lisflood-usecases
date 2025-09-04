import datetime
import functools
import glob
import os
import subprocess
import warnings
import xml.etree.ElementTree as ET
from pathlib import Path

import altair as alt
import ipyleaflet
import ipywidgets
import matplotlib.pyplot as plt
import netCDF4
import numpy as np
import pandas as pd
import cartopy.crs as ccrs
import cartopy.io.img_tiles as cimgt
from ipyfilechooser import FileChooser
from IPython.display import display
from matplotlib import rc

# dictionary with editable calibration parameters including allowed data range
parameters = {
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
optional_module_labels = {
    'InitLisflood': 'Initialize LISFLOOD',
    'InitLisfloodwithoutSplit': 'Initialize without Split',
    'gridSizeUserDefined': 'User-defined Grid Size',
    'SplitRouting': 'Split Routing',
    'inflow': 'External Inflow',
    'simulateReservoirs': 'Simulate Reservoirs',
    'simulateLakes': 'Simulate Lakes',
    'openwaterevapo': 'Open Water Evaporation',
    'drainedIrrigation': 'Drained Irrigation',
    'riceIrrigation': 'Rice Irrigation',
    'wateruse': 'Water Use',
    'useWaterDemandAveYear': 'Use Average Water Demand',
    'TransientWaterDemandChange': 'Transient Water Demand Change',
    'wateruseRegion': 'Water Use Region',
    'groundwaterSmooth': 'Groundwater Smoothing',
    'indicator': 'Indicator',
    'readNetcdfStack': 'Read NetCDF Stack',
    'writeNetcdf': 'Write NetCDF',
    'writeNetcdfStack': 'Write NetCDF Stack'
}

# Helper function to create module checkboxes
def _create_module_tab(root):
    """Parses XML and creates module checkbox widgets."""
    global optional_modules_xml
    global module_checkboxes

    module_checkboxes = {}
    optional_modules_xml = [root[i].find("./lfoptions") for i in range(2)]
    for element in optional_modules_xml[1]:
        module_name = element.attrib['name']
        display_name = optional_module_labels.get(module_name, module_name)
        module_checkboxes[module_name] = ipywidgets.Checkbox(
            value=bool(int(element.attrib['choice'])),
            description=display_name,
            disabled=False,
            style={'description_width': '0ex'}
            )
    return module_checkboxes

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
    for param_name, specs in parameters.items():
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
def show_settings(chooser, files_chosen):
    """
    Reads XML settings, creates and displays an interactive UI
    for configuring a LISFLOOD simulation.
    """
    if files_chosen[0].selected is None or files_chosen[1].selected is None:
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
    out_dir = Path(files_chosen[1].selected_path) / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    # opens settings file of PRE-RUN ([0]) and RUN ([1]) in list
    tree = [ET.parse(f.selected) for f in files_chosen]
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
    module_checkboxes = _create_module_tab(root)
    StepStart_picker, StepEnd_picker = _create_date_tab(root)
    output_grid = _create_output_tab(module_checkboxes)
    parameter_sliders = _create_parameter_tab(root)
    m, marker = _create_map(root, module_checkboxes)

    # Organize checkboxes for optional modules grid
    optional_modules_grid = ipywidgets.GridBox(
        [module_checkboxes[name] for name in optional_module_labels.keys()],
        layout=ipywidgets.Layout(grid_template_columns="33% 33% 33%")
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

    # Button to start processing method
    processing_button = ipywidgets.Button(description="Start processing")
    processing_button.on_click(functools.partial(on_processing_button_clicked, files_chosen=files_chosen))
    display(processing_button)

# callback function to write input data to XML files and start processing
def on_processing_button_clicked(b, files_chosen):
    """
    Updates XML settings filºes with user input and executes the LISFLOOD simulation.
    """
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
            if param_name in parameters:
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
        
        print(f"  - Writing updated settings to {files_chosen[i].selected}...")
        tree[i].write(files_chosen[i].selected)
        print(f"  - Successfully wrote settings to {files_chosen[i].selected}.")

    # Execute LISFLOOD pre-run and run
    print('\n--- LISFLOOD PRE-RUN ---')
    try:
        subprocess.run(
            ['lisflood', files_chosen[0].selected], 
            check=True, 
            capture_output=True, 
            text=True
        )
        print("PRE-RUN completed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error running LISFLOOD PRE-RUN:\n{e.stderr}")
        return
        
    print('\n--- LISFLOOD RUN ---')
    try:
        subprocess.run(
            ['lisflood', files_chosen[1].selected], 
            check=True, 
            capture_output=True, 
            text=True
        )
        print("RUN completed successfully.")
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

# returns element in NetCDF array
def subfinder(mylist, parameter):
    for i in range(len(mylist)):
        if mylist[i][0] == parameter:
            match = mylist[i][1]
    return match

# updates date of spatial plot from time slider
def update_time(date):
    global datasets
    global datevar
    global mm
    global parameter_dropdown
    
    mm.set_array(subfinder(datasets, parameter_dropdown.value)[parameter_dropdown.value][:][date].ravel())
    title = '{}: {}'.format(parameter_dropdown.value, datevar[0][date].strftime('%d %b %Y'))
    plt.title(title, size='xx-large')
    plt.draw()

#  updates parameter of spatial plot from dropdown menu
def update_parameter(parameter):
    global datasets
    global datevar
    global mm
    global cbar
    global date_slider
    
    mm.set_array(subfinder(datasets, parameter)[parameter][:][date_slider.value].ravel())
    mm.autoscale()
    cbar.update_normal(mm)
    title = '{}: {}'.format(parameter, datevar[0][date_slider.value].strftime('%d %b %Y'))
    plt.title(title, size='xx-large')
    plt.draw()

# adds CSV data to time series data frame
def addData(df, path, setting):
    df_temp = pd.read_csv(path, delim_whitespace=True, header=None)
    df_temp = df_temp.drop([0, 1, 2, 3], axis=0)
    df_temp = df_temp.drop([2, 3, 4, 5, 6, 7, 8, 9], axis=1)
    df_temp.columns = ['date', 'value']
    df_temp.insert(0, 'setting', [setting] * len(df_temp.index), True)

    return pd.concat([df, df_temp], axis=0, ignore_index=True)

# plots spatial and time series output data
def plot(chooser, output_dir):
    # sets path to output directory depending on function parameters
    if output_dir:
        path = chooser.selected_path
    else:
        path = os.path.join(chooser.selected_path, 'results')

    # checks whether output data is present
    if len(glob.glob('{}/*.nc'.format(path))) == 0 and len(glob.glob('{}/*.tss'.format(path))) == 0:
        print('No output files in {}.'.format(path))

    global datevar
    
    # checks for 'dis_run.tss' file
    if os.path.isfile('{}/dis_run.tss'.format(path)):
        # creates data frame and reads 'dis_run.tss'
        df = pd.DataFrame()
        df = addData(df, '{}/dis_run.tss'.format(path), 'Discharge')
        # if output was generated using the processing section of this notebook,
        # the calendar start day can be read from the XML file
        if 'CalendarDayStart' in globals():
            dates = []
            # Fix: Check for DtSec_xml to avoid NameError
            if 'DtSec_xml' in globals():
                DtSec = datetime.timedelta(seconds=int(DtSec_xml[1].attrib['value']))
                for factor in df['date']:
                    dates.append(CalendarDayStart + (int(factor) - 1) * DtSec)
                df['date'] = dates
        elif 'datevar' in globals():
            df['date'] = datevar[0].tolist()
        # if not, x-axis can not be reformated
        else:
            print('No reference data on CalendarDayStart to format x-axis of time series plot.')
        # plots data
        selection = alt.selection_multi(fields=['setting'], bind='legend')
        chart = alt.Chart(df
                ).mark_line(point=True
                ).encode(x='date:T',
                         y='value:Q',
                         color=alt.Color('setting', legend=alt.Legend(title="Setting")),
                         opacity=alt.condition(selection, alt.value(1), alt.value(0.2))
                ).add_selection(selection
                ).interactive(bind_y=False
                ).properties(width=800, height=300)
        # display outputs
        display(ipywidgets.HTML(value = f"<center><b><font size=5>{'Discharge Time Series'}</b></center>"))
        display(chart)

    # check for spatial output files in output folder
    if len(glob.glob('{}/*.nc'.format(path))) != 0:

        global datasets
        global date_slider
        global parameter_dropdown
        global mm
        global cbar
        
        # list of paths to  all spatial output files except avgdis and lzavin
        paths_datasets = list(filter(lambda number: (not number.endswith('avgdis.nc') and not number.endswith('lzavin.nc')),
                                     glob.glob('{}/*.nc'.format(path))))
        
        if 'datasets' in locals():
            datasets.clear()
        else:
            datasets = []

        i = 0
        # open netCDF datasets
        for dataset in paths_datasets:
            datasets.append([dataset.split('/')[-1].split('.')[0], netCDF4.Dataset(paths_datasets[i])])
            i = i + 1

        # get dates from NetCDF file
        try:
            # get calendar
            t_cal = datasets[0][1].variables['time'].calendar
        except AttributeError:
            t_cal = u"gregorian"
        datevar = []
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore")
            datevar.append(netCDF4.num2date(datasets[0][1].variables['time'][:],  # get values
                                        units=datasets[0][1].variables['time'].units,  # get unit
                                        calendar=t_cal))

        # create drowdown menu with all available outputs
        parameter_dropdown = ipywidgets.Dropdown(options=[item[0] for item in datasets], description='Parameter:')
        # create date slider for given time period
        date_slider = ipywidgets.IntSlider(min=0, max=len(datasets[0][1].dimensions['time']) - 1, step=1, value=0,
                                           description='Date:')
        # create simulation controls
        play = ipywidgets.Play(
            min=0,
            max=len(datasets[0][1].dimensions['time']) - 1,
            step=1,
            description="Press play",
            disabled=False
        )
        
        # get chosen parameter
        parameter = parameter_dropdown.value
        # create figure
        out_spatial = ipywidgets.Output()
        with out_spatial:
            # create figure with open street map
            request = cimgt.OSM()
            fig, ax = plt.subplots(figsize=(8,4), subplot_kw=dict(projection=request.crs))
            ax.add_image(request, 8)
            cmap = plt.cm.cool
            vmin = np.min(subfinder(datasets, parameter)[parameter][:])
            vmax = np.max(subfinder(datasets, parameter)[parameter][:])
            #vmax = np.percentile(subfinder(datasets, parameter)[parameter][:], 97.5)
            mm = ax.pcolormesh(subfinder(datasets, parameter)['lon'][:],
                               subfinder(datasets, parameter)['lat'][:],
                               subfinder(datasets, parameter)[parameter][:][0],
                               vmin=vmin,
                               vmax=vmax,
                               transform=ccrs.PlateCarree(),
                               cmap=cmap,
                               alpha=0.5)
            cbar = plt.colorbar(mm, shrink=0.7)
            cbar.ax.tick_params(labelsize=17)
            update_time(0)
            
        # update plot when user changes parameter in dropdown menu
        ipywidgets.interactive(update_parameter, parameter=parameter_dropdown)
        # update plot when user changes date slider
        ipywidgets.interactive(update_time, date=date_slider)
        # update plot when user starts simulation
        ipywidgets.jslink((play, 'value'), (date_slider, 'value'))

        # display outputs
        display(ipywidgets.HTML(value = f"<center><b><font size=5>{'Spatial Outputs'}</b></center>"))
        display(out_spatial)
        display(ipywidgets.HBox([play, date_slider, parameter_dropdown]))
        print('\n\n\n\n\n\n\n\n')