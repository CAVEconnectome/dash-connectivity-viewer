import os

###########################################
### Default data and request parameters ###
###########################################
def parse_environ_vector(input, num_type):
    return [num_type(x) for x in input.split(",")]


DEFAULT_DATASTACK = os.environ.get("DEFAULT_DATASTACK")
DEFAULT_SERVER_ADDRESS = os.environ.get("DEFAULT_SERVER_ADDRESS")

# Sets how cell type and soma location information is chunked for multithreaded queries
TARGET_ROOT_ID_PER_CALL = os.environ.get("TARGET_ROOT_ID_PER_CALL", 200)
MAX_CHUNKS = os.environ.get("MAX_CHUNKS", 20)

VOXEL_RESOLUTION = os.environ.get("VOXEL_RESOLUTION")
if VOXEL_RESOLUTION is not None:
    voxel_resolution = parse_environ_vector(VOXEL_RESOLUTION, float)
else:
    voxel_resolution = None
##############################
### Link generation limits ###
##############################

# Length of dataframe allowed for automatic table link generation
MAX_DATAFRAME_LENGTH = os.environ.get("MAX_DATAFRAME_LENGTH", 8_000)

# Length of dataframe before switching over to manual link shortener
MAX_SERVER_DATAFRAME_LENGTH = os.environ.get("MAX_SERVER_DATAFRAME_LENGTH", 20_000)

##################
### Key tables ###
##################

# Used to look up 'Nucleus Id'
NUCLEUS_TABLE = os.environ.get("NUCLEUS_TABLE")
NUCLEUS_ID_COLUMN = os.environ.get("NUCLEUS_ID_COLUMN", "id")

# Used to look up number of neurons per root id
soma_table = os.environ.get("SOMA_TABLE", NUCLEUS_TABLE)

# Used to look up connectivity
SYNAPSE_TABLE = os.environ.get("SYNAPSE_TABLE")

####################
### Column names ###
####################

syn_pt_position_col = os.environ.get("SYN_POSITION_COLUMN", "ctr_pt")
cell_pt_position_col = os.environ.get("SOMA_POSITION_COLUMN", "pt")

ct_col = os.environ.get("SOMA_CELL_TYPE_COLUMN", "cell_type")
soma_table_cell_category = os.environ.get("SOMA_TABLE_CELL_TYPE")
if ct_col and soma_table_cell_category:
    soma_table_query = f"{ct_col} == '{soma_table_cell_category}'"
else:
    soma_table_query = None

num_soma_col = "num"
num_syn_col = "num_syn"
net_size_col = "net_syn_size"
mean_size_col = "mean_syn_size"
root_id_col = "root_id"
own_soma_col = "own_soma_pt_position"
soma_position_col = "soma_pt_position"


def bound_pt_position(pt):
    return f"{pt}_position"


def bound_pt_root_id(pt):
    return f"{pt}_root_id"