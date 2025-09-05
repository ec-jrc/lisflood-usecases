from datetime import datetime, date
import functools
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Union
import logging

import altair as alt
import ipyleaflet
import ipywidgets
import matplotlib.pyplot as plt
import pandas as pd
import xarray as xr
import cartopy.crs as ccrs
import cartopy.io.img_tiles as cimgt
from ipyfilechooser import FileChooser
from IPython.display import display
# from matplotlib import rc

from docs.lisflood_read_plot import read_tss

# Configure the logging to output messages to the console
logging.basicConfig(level=logging.INFO)

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
def _create_module_tab(roots):
    """
    Parses XML and creates module checkbox widgets, organized by group,
    using a single source of truth.
    """
    global lfoptions_xml
    global module_checkboxes

    module_checkboxes = {}
    lfoptions_xml = {run: root.find("./lfoptions") for run, root in roots.items()}

    # First, create all the checkboxes and store them in the global dictionary
    for element in lfoptions_xml['run']:
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
def _create_date_tab(roots):
    """Parses XML dates and creates date picker widgets."""
    global starts
    global ends
    
    common_widget_style = {
        'layout': ipywidgets.Layout(width='40%'), 
        'style': {'description_width': '25ex'}
    }
    run_names = {
        'pre-run': 'Pre-run',
        'run': 'Run'
    }

    # extract, format and create picker for the start dates
    starts = {
        run: root.find("./lfuser/group/textvar[@name='StepStart']") 
        for run, root in roots.items()
    }
    starts_iso = {
        run: datetime.strptime(start.attrib['value'].split()[0], '%d/%m/%Y').strftime('%Y-%m-%d') 
        for run, start in starts.items()
    }
    start_picker = {
        run: ipywidgets.DatePicker(
            description='{0:>7} | {1:<10}'.format(run_names[run], 'Start date'),
            value=date.fromisoformat(start),
            **common_widget_style
        ) for run, start in starts_iso.items()
    }

    # extract, format and create picker for the end dates
    ends = {
        run: root.find("./lfuser/group/textvar[@name='StepEnd']") 
        for run, root in roots.items()
    }
    ends_iso = {
        run: datetime.strptime(end.attrib['value'].split()[0], '%d/%m/%Y').strftime('%Y-%m-%d')
        for run, end in ends.items()
    }
    end_picker = {
        run: ipywidgets.DatePicker(
            description='{0:>7} | {1:<10}'.format(run_names[run], 'End date'),
            value=date.fromisoformat(end),
            **common_widget_style
        ) for run, end in ends_iso.items()
    }

    return start_picker, end_picker

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
def _create_parameter_tab(roots):
    """Parses XML and creates calibration slider widgets."""
    global lfuser_xml
    global parameter_sliders

    parameter_sliders = {}
    lfuser_xml = {run: root.find("./lfuser") for run, root in roots.items()}
    if lfuser_xml['run'] is None:
        logging.error("Could not find `lfuser` group in the RUN settings file")
        return {}

    # Iterate through the desired order to create the sliders
    for param_name, specs in parameter.items():
        element = lfuser_xml['run'].find(f".//textvar[@name='{param_name}']")
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
def _create_map(roots, module_checkboxes):
    """Initializes and configures the ipyleaflet map widget."""
    global m
    global marker
    global coordinates

    coordinates = {run: root.findall("./lfuser/group/textvar/[@name='Gauges']")[0] for run, root in roots.items()}
    lon, lat = coordinates['run'].attrib['value'].split()
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
def lisflood_interface(chooser, settings_files):
    """
    Reads XML settings, creates and displays an interactive UI
    for configuring a LISFLOOD simulation.
    """
    if settings_files['pre-run'].selected is None or settings_files['run'].selected is None:
        return

    global trees
    global CalendarDayStart
    global timestep_xml
    global timestep_box
    global lfoptions_xml
    global lfuser_xml
    global parameter_sliders
    global module_checkboxes
    global m
    global marker
    global coordinates
    global start_picker
    global end_picker

    # Create output folder if it does not exist
    out_dir = Path(settings_files['run'].selected_path) / "results"
    out_dir.mkdir(parents=True, exist_ok=True)

    # opens settings file of PRE-RUN ([0]) and RUN ([1]) in list
    trees = {run: ET.parse(file.selected) for run, file in settings_files.items()}
    roots = {run: tree.getroot() for run, tree in trees.items()}

    # gets timestep
    timestep_xml = {run: root.find("./lfuser/group/textvar[@name='DtSec']") for run, root in roots.items()}
    if timestep_xml['pre-run'] is None:
        logging.error("Could not find 'DtSec' in the PRE-RUN settings file.\nPlease, check the file and the XML path.")
        return 
    timestep_box = ipywidgets.BoundedIntText(
        value=timestep_xml['pre-run'].attrib['value'],
        min=1,
        max=31536000,
        step=60,
        description='Timestep [s]:',
        layout=ipywidgets.Layout(width='40%'),
        style={'description_width': '25ex'}
    )

    # gets calendar day start
    calendar_day_start_element = roots['run'].find("./lfuser/group/textvar[@name='CalendarDayStart']")
    if calendar_day_start_element is None:
        logging.error("Could not find 'CalendarDayStart' in the RUN settings file.\nPlease, check the file and the XML path.")
        return
    date_time_str = calendar_day_start_element.attrib['value']
    CalendarDayStart = datetime.strptime(date_time_str, '%d/%m/%Y %H:%M')

    # Create UI widgets
    grouped_module_vboxes = _create_module_tab(roots)
    start_picker, end_picker = _create_date_tab(roots)
    output_grid = _create_output_tab(module_checkboxes)
    parameter_sliders = _create_parameter_tab(roots)
    m, marker = _create_map(roots, module_checkboxes)

    # Organize grouped module vboxes into a single GridBox
    optional_modules_grid = ipywidgets.GridBox(
        grouped_module_vboxes,
        layout=ipywidgets.Layout(grid_template_columns="repeat(2, 1fr) 1fr")
    )

    # Define UI layout and tabs
    tabs = ipywidgets.Tab()
    tabs.children = [
        ipywidgets.VBox([optional_modules_grid]),
        ipywidgets.VBox([start_picker['pre-run'], end_picker['pre-run'], start_picker['run'], end_picker['run'], timestep_box]),
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

    # display the output widget
    display(output_area)

# callback function to write input data to XML files and start processing
def on_processing_button_clicked(b, settings_files, output_area):
    """
    Updates XML settings filºes with user input and executes the LISFLOOD simulation.
    """
    # Clear previous output before each run
    output_area.clear_output()

    with output_area:
        print("Start processing.")

        global datasets
        global lfuser_xml
        global parameter_sliders
        global lfoptions_xml
        global module_checkboxes
        global trees
        global starts
        global ends
        global timestep_xml
        global timestep_box
        global coordinates
        global marker
        global start_picker
        global end_picker

        # Check if 'datasets' exists and close any open NetCDF files
        logging.debug("Checking for previous datasets...")
        if 'datasets' in globals():
            for _, dataset in datasets:
                dataset.close()
            datasets.clear()
            logging.warning("Closed and cleared previous datasets.")
        else:
            datasets = []
            logging.debug("No previous datasets found.")
        
        # Update calibration parameter values in XML from sliders
        print("\nUpdate calibration parameters:\n")
        for run, root_xml in lfuser_xml.items():
            textvar_elements = root_xml.findall(".//textvar")
            for element in textvar_elements:
                param_name = element.attrib['name']
                if param_name in parameter:
                    new_value = parameter_sliders[param_name].children[0].value
                    element.attrib['value'] = str(new_value)
                    print(f"\t{param_name:>25} = {new_value:.3f}")

        # Update optional module choices in XML from checkboxes
        print('\nUpdate optional modules:\n')
        for run, root_xml in lfoptions_xml.items():
            for element in root_xml:
                if element.tag == 'setoption':
                    module_name = element.attrib['name']
                    new_choice = int(module_checkboxes[module_name].value)
                    element.attrib['choice'] = str(new_choice)
                    if new_choice == 1:
                        print(f"\t{module_name:>25} : active")

        # Configure SplitRouting and InitLisflood options in both XML files
        split_routing = module_checkboxes['SplitRouting'].value
        print(f"\nUpdate routing options:\n")
        for run, root_xml in lfoptions_xml.items():  
            # Determine and set the correct InitLisflood choice based on split_routing
            init_lisflood_choice = split_routing and (run == 'pre-run')
            init_lisflood_without_split_choice = not split_routing and (run == 'run')

            root_xml.findall("setoption[@name='SplitRouting']")[0].attrib['choice'] = str(int(split_routing))
            root_xml.findall("setoption[@name='InitLisflood']")[0].attrib['choice'] = str(int(init_lisflood_choice))
            root_xml.findall("setoption[@name='InitLisfloodwithoutSplit']")[0].attrib['choice'] = str(int(init_lisflood_without_split_choice))
            print(
                f"\t{run.upper()}:\n"
                f"\t{'InitLisflood':>25} : {'active' if init_lisflood_choice else 'disabled'}\n"
                f"\t{'InitLisfloodwithoutSplit':>25} : {'active' if init_lisflood_without_split_choice else 'disabled'}"
            )

        # Write simulation dates, timestep, and coordinates to both XML files
        print("\nUpdate simulation dates, timestep, and coordinates")
        for run, tree in trees.items():
            date_format_in = "%Y-%m-%d"
            date_format_out = '%d/%m/%Y'
            
            start_date = start_picker[run].value
            start_date_formatted = datetime.strptime(str(start_date), date_format_in).strftime(date_format_out)
            starts[run].attrib['value'] = f"{start_date_formatted} {starts[run].attrib['value'].split()[1]}"

            end_date = end_picker[run].value
            end_date_formatted = datetime.strptime(str(end_date), date_format_in).strftime(date_format_out)
            ends[run].attrib['value'] = f"{end_date_formatted} {ends[run].attrib['value'].split()[1]}"

            timestep = timestep_box.value
            timestep_xml[run].attrib['value'] = str(timestep)

            if module_checkboxes['repDischargeTs'].value:
                coordinates[run].attrib['value'] = f"{marker.location[1]} {marker.location[0]}"

            print(
                f"\n\t{run.upper()}:\n"
                f"\t{'Start':>25} : {start_date}\n"
                f"\t{'End':>25} : {end_date}\n"
                f"\t{'Time step':>25} : {timestep} (s)\n"
            )
            
        # logging.info(f"  - Writing updated settings to {settings_files[run].selected}...")
        print('\nUpdate settings files:\n')
        for run, tree in trees.items():
            tree.write(settings_files[run].selected)
            print(f"\t{run.upper():>8} : {settings_files[run].selected}.")

        # Execute LISFLOOD pre-run and run
        print('\n\n--- LISFLOOD PRE-RUN ---\n')
        try:
            result = subprocess.run(['lisflood', settings_files['pre-run'].selected], check=True, capture_output=True, text=True)
            print("PRE-RUN completed successfully.")
            if result.stdout:
                print("LISFLOOD stdout:")
                print(result.stdout)
        except subprocess.CalledProcessError as e:
            logging.error(f"Running LISFLOOD PRE-RUN:\n{e.stderr}")
            return
            
        print('\n\n--- LISFLOOD RUN ---\n')
        try:
            result = subprocess.run(['lisflood', settings_files['run'].selected], check=True, capture_output=True, text=True)
            print("RUN completed successfully.")
            if result.stdout:
                print("LISFLOOD stdout:")
                print(result.stdout)
        except subprocess.CalledProcessError as e:
            logging.error(f"Running LISFLOOD RUN:\n{e.stderr}")
            return
            
        print("\nEnd of the processing.")

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
        logging.warning(f'No output files in {path_results}.')
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
        logging.warning(f'No NetCDF files in the results folder: {path_results}.')
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