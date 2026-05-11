"""Global pytest configuration — suppress known third-party deprecation warnings."""
import warnings

collect_ignore = ["scripts/full_integration_test.py"]

try:
    from pandas.errors import Pandas4Warning
    warnings.filterwarnings("ignore", category=Pandas4Warning)
except ImportError:
    pass

# pandas_ta sets deprecated copy_on_write option
warnings.filterwarnings("ignore", message=".*copy_on_write.*", category=DeprecationWarning)
# pandas_ta ichimoku uses deprecated 'd' frequency alias
warnings.filterwarnings("ignore", message=".*'d' is deprecated.*", category=FutureWarning)
