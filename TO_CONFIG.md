# Configuration

Environmental variables that need to be set

## Common

These values apply to multiple tools in the repo.

### Required

* `DEFAULT_DATASTACK` : datastack to use for looking up info/creating the CAVE client

* `DEFAULT_SERVER_ADDRESS` : name of the global server for the CAVEclient

### Optional

There are three categories of optional parameters.

#### If left unset, inferred by info service

* `VOXEL_RESOLUTION` : voxel resolution to use for the viewer, as three numbers separated by commas with no spaces. Can also be looked up from the info service, which is preferable.

* `SYNAPSE_TABLE` : Name of the synapse table. Can be inferred from the info service of the datastack.

* `NUCLEUS_TABLE` : Table name to use for querying nucleus ids, which are stable per-cell ids used for things like counting the number of distinct soma per root id.

#### Set if nucleus table is not all neurons

* `SOMA_TABLE_CELL_TYPE` : If the soma table has cell type information, this is the value to restrict rows to when assigning cell location. Omit if no filtering is necessary.

* `SOMA_CELL_TYPE_COLUMN` : Column to use to define cell types when querying the soma table for neurons. Default is `cell_type`.

The net result is that the dataframe is filtered accoridng to `df.query()`

#### Adapt to schema used for synapse and soma table

* `SYN_POSITION_COLUMN` : Bound point name in the synapse schema to use for defining synapse position. Default is `ctr_pt`, but this may not exist for all datasets. Note that only the prefix should be provided, not the `_position` suffix.

* `SOMA_POSITION_COLUMN` : Bound point name in the Nucleus table to use for defining cell location. Default is `pt`. Note that only the prefix should be provided, not the `_position` suffix.

#### Defaults that are set for performance

* `TARGET_ROOT_ID_PER_CALL` : Some parts of the synapse queries are multithreaded (to get number of associated soma), and this parameter sets the root ids per cell. By default 200.

* `MAX_DATAFRAME_LENGTH` : Limit of dataframe size for automatic table link generation. Default is 8,000.

* `MAX_SERVER_DATAFRAME_LENGTH` : Length of dataframe before switching over to the link shortener. Default is 20,000.


## Cell Type Connectivity

The configuration of this app is spread across both environmental variables and a config dictionary that is passed when the app is initially run.

### Config dictionary

Each item here is a key in a dictionary, with values described. All are lower case with underscores.

* `cell_type_dropdown_options` : This item allows you to optionally configure readable names for certain tables. It is a list of dicts, with each item having two keys, `label` and `value`. The value of `label` is the readable name, the value of `value` is the table name in the database. Optional.

* `omit_cell_type_tables` : A list of table names to exclude from the cell type dropdown.

* `valence_map_table`: This item describes how to convert table data into excitatory/inhibitory valence information, specific to each table. It is a dict with keys being annotation table names and values being a list of three elements, the first being a column name, the second being the value in the column that indicates an excitatory cell, and the third being a the value in the colume that indicates an inhibitory cell.

* `cell_type_column_schema_lookup` : This item is a dict mapping schema names as keys to the column name to use to indicate cell type in the table. This is how it will work to use additional schema for the cell typing, but this feature is not yet tested and probably won't work out of the box. At the moment, the value should be:

        ```python
        {
            "cell_type_local": "cell_type",
        },
        ```

* `default_cell_type_dropdown` : The value is the table name to select by default when loading the page fresh.

### Environmental variables

All environment variables are optional.

* `CT_CONN_CELL_TYPE_COLUMN` : Defines the name of the cell type column to be displayed, by default `cell_type`.

* `CT_CONN_SOMA_DEPTH_COLUMN` : Defines the name of the soma depth column to be displayed, by default `soma_depth`.

* `CT_CONN_IS_INHIBITORY_COLUMN` : Defines the name of the column displaying a boolean value for a cell being inhibitory, by default `is_inhibitory`.

* `CT_CONN_SHOW_DEPTH_PLOTS` : If `true` (default), make plots using soma depth.

* `CT_CONN_CELL_TYPE_SCHEMA` : Comma-separated list of schema names to allow in the cell types table. This is temporary until additional schema are tested and working, at which point it will be set by the config (see above).

* `CT_CONN_DENDRITE_COLOR` : Comma-separated floating point rgb values to use for the postsynaptic color in the violin plot.

* `CT_CONN_AXON_COLOR` : Comma-separated floating point rgb values to use for the presynaptic color in the violin plot.

* `CT_CONN_E_PALETTE`/`CT_CONN_E_PALETTE`/`CT_CONN_U_PALETTE` : Seaborn color palette to use to set a range of colors for excitatory/inhibitory/unknown target cells. By default, `RdPu`, `Greens`, and `Greys`.

* `CT_CONN_PALETTE_BASE` : Number between 0 and 8 that sets which item in the palette to draw the main color from. By default, 6.

## Cell Type Table

### Environmental Variables 

* `CT_CELL_TYPE_SCHEMA` : Specify the name of the cell type schema to use. Currently only one value is allowed, and the default of `cell_type_local` is what is expected.