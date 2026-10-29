# Passenger data setup

Place the five supplied TfL NUMBAT 2025 files here without renaming them:

- `NBT25MON_Outputs.xlsx`
- `NBT25TWT_Outputs.xlsx`
- `NBT25FRI_Outputs.xlsx`
- `NBT25SAT_Outputs.xlsx`
- `NBT25SUN_Outputs.xlsx`

These workbooks are excluded from Git. Obtain the matching source files separately; the application does not download them. See the [TfL data portal](https://crowding.data.tfl.gov.uk/) for source information and availability. A differently structured release may require changes to the loader.

The application reads the files and writes derived caches under `cache/`; it does not modify the workbooks. Tuesday, Wednesday and Thursday use the shared TWT workbook.
