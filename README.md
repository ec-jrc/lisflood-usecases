# Lisflood use cases

This repository hosts two use cases for the LISFLOOD model. The purpose of those use cases is for you to get kick-started with LISFLOOD as well as to give you the opportunity to verify that the model is running correctly on your PC. For you to be able to do that we have prepared for each of the two use cases all the static input maps, the meteorological forcings and the LISFLOOD setting files. Once you have downloaded and installed the LISFLOOD model on your own PC, we recommend you to download also one (or both) of the use cases and run as a test on your PC. In order for you to know that everything has worked correctly we have uploaded the reference output file. If everything has worked correctly your output file is identical to the reference one.

Before getting started with the description and instruction on the use cases, here again the link to the [Lisflood OS landing page](https://ec-jrc.github.io/lisflood/) for more information on the model and affiliated tools.


## Use case 1: Fraser River, British Columbia, Canada  <a id="usecase1"></a>

### Short description 
The first use case is located in West Canada, in a basin called Fraser. The Fraser River rises at Fraser Pass near Blackrock Mountain in the Rocky Mountains and discharges into the Pacific Ocean at the city of Vancouver. With its 1,375 km length, it is the longest river within British Columbia and the 11<sup>th</sup> longest river in Canada. The basin size is about 220,000 km<sup>2</sup>, while the annual discharge at its mouth is 3,550 m<sup>3</sup>.

![](doc/FraserRiver.png)

For testing the LISFLOOD code we prepared all the required input (maps) for a subsection of the Fraser basin (see red dashed box in Figure above). The maps cover the river section from the Nechako tributary in the North till the Quesnel tributary in the South. The outlet point of our test case is located on the main Fraser river at the hight of the Quesnel city and has an upstream area of 114,00 km<sup>2</sup>. As our subsection covers only a relatively small portion of the outlet's upstream catchment, four inlet points have been implemented (called Shelley, Isle Pierre, near Cinema and near Quesnel) accounting for the discharge (of the Upper Fraser, Nechako, Blackwater and Quesnel river respectively) prior to "inflowing" into our map area.   

As this is a use case from our global setup, all input maps are in the geographical system WGS84, with latitude and longitude. The map extent is 52.6<sup>o</sup> to 54<sup>o</sup> North and -121.4<sup>o</sup> to -124.5<sup>o</sup> West, with a horizontal resolution of 0.1 degree. The standard map format is netCDF.


### How to get it running
There are several important components of this use case that you can find in the parent folder:
- [pre edited LISFLOOD settings files](https://github.com/ec-jrc/lisflood-usecases/tree/master/LF_lat_lon_UseCase): two files: *settings_LF_CUT-PreRun000758494230.xml* for the warm up and *settings_LF_CUT-Run000758494230.xml* for the actual running
- [static maps of the Fraser river subsection](https://github.com/ec-jrc/lisflood-usecases/tree/master/LF_lat_lon_UseCase/maps), with everything included e.g. soil-, landuse-, topography-, etc. related information
- meteorological input data from 02.01.1986 till 01.01.2018
- [reference output](https://github.com/ec-jrc/lisflood-usecases/blob/master/LF_lat_lon_UseCase/streamflow_simulated_best.csv), to check that everything went correctly

## Use case 2: Po River, Italy <a id="usecase2"></a>

### Short description 
The second use case is located in North Italy, in the Po River Basin. Its spring is at Monte Viso in Piemonte (Italy) at about 3,700 m; from there it flows 652 km eastwards till it flows into the Adriatic Sea close to Venice. The whole basin covers about 74,000 km², of which 70,000 km² are on Italian territory, and the remaining are shared between France and Switzerland. The average annual discharge at the river mouth is about 1,540 m³/s, whereas the maximum is about double of that.

![](doc/PoRiver.png)

Also for this use case we have selected only a portion of the whole river basin. You can see the selected area in the map above as it is outlined with a red dashed box. It includes a large part of the Upper Po River basin till the maps outlet at Pieve del Cairo on the main Po River. The upstream area of the maps outlet is 25,875 km². However, as not all of the very upstream sections are fully included in the map extent (you see that some are outside of the red box) five inflow points were defined (see map). At those locations a pre-calculated discharge time series will be used that accounts also for all the upstream areas.

As this use case is from our European setup, all the input maps are in the SPIRE compliant ETRS89 Lambert Azimuthal Equal Area Coordinate Reference System (ETRS-LAEA). The extent of the prepared input maps for this use case is 2535000 (top), 4095000 (left), 4230000 (right) and 2380000 (bottom). The horizontal resolution is 5 km and the standard map format is netCDF.


### How to get it running
There are several important components of this use case that you can find in the parent folder:
- [pre edited LISFLOOD settings files](https://github.com/ec-jrc/lisflood-usecases/tree/master/LF_ETRS89_UseCase): two files: *settings_LF_CUT-PreRun009026175600.xml* for the warm up and *settings_LF_CUT-Run009026175600.xml* for the actual running
- [static maps of the Po river subsection](https://github.com/ec-jrc/lisflood-usecases/tree/master/LF_ETRS89_UseCase/maps), with everything included e.g. soil-, landuse-, topography-, etc. related information
- meteorological input data from 02.01.1990 till 31.12.2017
- [reference output](https://github.com/ec-jrc/lisflood-usecases/blob/master/LF_ETRS89_UseCase/streamflow_simulated_best.csv), to check that everything went correctly

