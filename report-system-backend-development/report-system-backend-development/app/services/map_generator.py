import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle, RegularPolygon
from matplotlib import patheffects
from shapely.geometry import Point, box
from typing import List, Dict, Any
from pathlib import Path
import os
import numpy as np
import math
import contextily as ctx
from adjustText import adjust_text

# Configure contextily timeout
os.environ['CONTEXTILY_TIMEOUT'] = '30'

# Suppress joblib cache warnings (tiles still download fine, warnings are harmless)
import warnings
warnings.filterwarnings('ignore', message='.*Unable to cache to disk.*')
warnings.filterwarnings('ignore', category=UserWarning, module='joblib')

# ============================================================================
# CONFIGURATION CONSTANTS
# ============================================================================

# Color palette
COLORS = {
    'background': '#D4E8DE',
    'water_polygon': '#00C5FF',
    'river_lines': '#00C5FF',
    'boundaries': '#9B9B9B',
    'boundaries_fill': '#D9FCD6',
    'pipeline': '#FF00C5',
    'pipeline_markers': '#FF00C5',
    'settlement_label': '#000000',
}

# Map dimensions and DPI
DPI = 300
PAGE_WIDTH_INCHES = 12
PAGE_HEIGHT_INCHES = 14

# Map extent and buffer settings
TARGET_ASPECT_RATIO = 0.7  # FIXED aspect ratio (height/width) - zoom adjusts to fit pipeline
EXTRA_BUFFER_PCT = 0.05  # Reduced from 0.50 to minimize padding
VERTICAL_BUFFER_PCT = 0.03  # Reduced from 0.12
HORIZONTAL_BUFFER_PCT = 0.03  # Reduced from 0.12

# Marker and symbol sizes (as percentage of map width)
PIPELINE_MARKER_RADIUS_PCT = 0.002
INCIDENT_MARKER_RADIUS_PCT = 0.01  # Original size
SETTLEMENT_MARKER_SIZE_PCT = 0.0005
OPERATION_BASE_HEXAGON_RADIUS_PCT = 0.015

# Text and label offsets (as percentage of map dimensions)
TEXT_OFFSET_X_PCT = 0.001
CALLOUT_OFFSET_X_PCT = 0.06
CALLOUT_OFFSET_Y_PCT = 0.015

# North arrow and scale bar settings
ARROW_MARGIN_PCT = 0.03
ARROW_SIZE_PX = 14
ARROW_WIDTH_MULTIPLIER = 25
SCALE_BAR_TARGET_KM = 5
SCALE_BAR_TICK_HEIGHT_PCT = 0.005

# Pipeline marker spacing
PIPELINE_MARKER_SPACING_PCT = 0.03

# Settlement label settings
SETTLEMENT_LABEL_FONTSIZE = 6
SETTLEMENT_LABEL_OFFSET_MULTIPLIER = 3
MIN_LABEL_DISTANCE_PCT = 0.035
BOUNDARY_MARGIN_PCT = 0.05

# Operation base settings  
OPERATION_BASE_LABEL_FONTSIZE = 15
OPERATION_BASE_LABEL_OFFSET_PCT = 0.02

# Pipeline label settings
PIPELINE_LABEL_FONTSIZE = 9
PIPELINE_LABEL_FONTSIZE_LONG = 7
PIPELINE_LABEL_MAX_LENGTH = 25
PIPELINE_LABEL_OFFSET_PCT = 0.025
PIPELINE_LABEL_POSITION_FRACTION = 0.6
PIPELINE_LABEL_ANGLE_SAMPLE_PCT = 0.02

# Incident marker settings
INCIDENT_MARKER_FONTSIZE = 15
INCIDENT_MARKER_LINEWIDTH = 2.5

# Layer rendering settings (linewidths)
BOUNDARY_LINEWIDTH = 2.0
SEA_LINEWIDTH = 1.5
RIVER_POLY_LINEWIDTH = 1
RIVER_LINE_LINEWIDTH = 1.5
MINOR_RIVER_LINEWIDTH = 1
PIPELINE_LINEWIDTH = 2
PIPELINE_MARKER_LINEWIDTH = 1

# Satellite map specific settings
SATELLITE_ZOOM_LEVEL = 11
SATELLITE_NODE_SIZE_PCT = 0.012
SATELLITE_MARKER_SPACING_PCT = 0.06
SATELLITE_INCIDENT_MARKER_RADIUS_PCT = 0.009
SATELLITE_INCIDENT_FONTSIZE = 9
SATELLITE_INCIDENT_OUTLINE_WIDTH = 3
FONT_FAMILY = 'Cambria'
# Incident categories with color coding
INCIDENT_CATEGORIES = {
    'pipeline_damage': {
        'code': 'PDM',
        'color': '#FF3366',
        'name': 'Pipeline Damage',
        'keywords': ['damage', 'broken', 'rupture', 'crack', 'breach', 'hole', 'burst', 'puncture']
    },
    'leak': {
        'code': 'LEK',
        'color': '#FF9500',
        'name': 'Leak/Spill',
        'keywords': ['leak', 'spill', 'seepage', 'discharge', 'escape', 'emission']
    },
    'corrosion': {
        'code': 'COR',
        'color': '#FFD700',
        'name': 'Corrosion',
        'keywords': ['corrosion', 'rust', 'degradation', 'deterioration', 'oxidation', 'erosion']
    },
    'encroachment': {
        'code': 'ENC',
        'color': '#9D4EDD',
        'name': 'Encroachment',
        'keywords': ['encroachment', 'illegal', 'trespass', 'unauthorized', 'intrusion', 'invasion', 'settlement', 'building']
    },
    'vegetation': {
        'code': 'VEG',
        'color': '#06D6A0',
        'name': 'Vegetation Overgrowth',
        'keywords': ['vegetation', 'overgrowth', 'weed', 'plant', 'grass', 'tree', 'shrub', 'bush']
    },
    'third_party': {
        'code': 'TPD',
        'color': '#E91E63',
        'name': 'Third Party Activity',
        'keywords': ['third party', 'construction', 'excavation', 'digging', 'drilling', 'machinery']
    },
    'washout': {
        'code': 'WSH',
        'color': '#00B4D8',
        'name': 'Erosion/Washout',
        'keywords': ['erosion', 'washout', 'exposed', 'uncovered', 'flood', 'water', 'river']
    },
    'vandalism': {
        'code': 'VAN',
        'color': '#DC143C',
        'name': 'Vandalism/Theft',
        'keywords': ['vandalism', 'theft', 'stolen', 'sabotage', 'tampering', 'vandal']
    },
    'marker': {
        'code': 'MRK',
        'color': '#FFEA00',
        'name': 'Marker/Sign Issue',
        'keywords': ['marker', 'sign', 'signage', 'post', 'warning', 'indicator']
    },
    'other': {
        'code': 'OTH',
        'color': '#9E9E9E',
        'name': 'Other/Uncategorized',
        'keywords': []
    }
}

# Esri satellite imagery URL
ESRI_SATELLITE_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def categorize_incident(description: str) -> dict:
    """Categorize an incident based on keywords in its description"""
    if not description:
        return INCIDENT_CATEGORIES['other']

    description_lower = description.lower()

    for category_key, category_data in INCIDENT_CATEGORIES.items():
        if category_key == 'other':
            continue

        for keyword in category_data['keywords']:
            if keyword.lower() in description_lower:
                return category_data

    return INCIDENT_CATEGORIES['other']


def darken_color(hex_color: str, factor: float = 0.6) -> str:
    """Darken a hex color by a given factor"""
    hex_color = hex_color.lstrip('#')
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)

    r = int(r * factor)
    g = int(g * factor)
    b = int(b * factor)

    return f'#{r:02x}{g:02x}{b:02x}'


def generate_incident_legend(incidents: List[Dict[str, Any]], output_path: str) -> str:
    """
    Generate a compact, ArcGIS Pro–style incident legend as a PNG.
    - Width: 4 inches (one third of 12")
    - Bold typography
    - Wrapped description text
    - Tilted-square (diamond) symbols
    """
    print("🎨 Generating compact incident legend (4-inch width)...")

    # Categorize and count
    categorized_incidents = []
    category_counts = {}
    for inc in incidents:
        category = categorize_incident(inc.get('description', ''))
        inc_with_category = inc.copy()
        inc_with_category['category'] = category
        categorized_incidents.append(inc_with_category)

        cat_key = category['code']
        if cat_key not in category_counts:
            category_counts[cat_key] = {
                'count': 0,
                'category': category,
                'incidents': []
            }
        category_counts[cat_key]['count'] += 1
        category_counts[cat_key]['incidents'].append(inc_with_category)

    num_incidents = len(categorized_incidents)

    # Layout parameters for narrow legend
    dpi = 150
    fig_width_in = 1.0  # one third of 12"
    side_margin_pct = 6         # percent of 0-100 axis
    top_margin_pct = 6
    bottom_margin_pct = 8

    # Row sizing: compact
    row_height_pct = 4.8        # vertical space per incident row (percent of 0-100 axis)
    header_height_pct = 9
    footer_block_pct = 12

    # Compute figure height from content
    content_height_pct = header_height_pct + (num_incidents * row_height_pct) + footer_block_pct
    total_height_pct = content_height_pct + top_margin_pct + bottom_margin_pct

    # Convert virtual 0-100 canvas to inches approximately
    # We aim for total virtual height = 100; scale height to keep content density consistent
    scale = max(total_height_pct / 100.0, 1.0)
    fig_height_in = 8.0 * scale  # base guess; scales up if more rows

    # MAKE IT SQUARE: height = width
    fig_size = max(fig_width_in, fig_height_in)  # Use the larger dimension for both

    fig, ax = plt.subplots(figsize=(fig_size, fig_size), dpi=dpi)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis('off')

    # Title
    ax.text(50, 100 - top_margin_pct + 1.0,
            'INCIDENT LEGEND',
            fontsize=14, weight='bold', ha='center', va='top', color='#111111')

    # Column positions (percent of width) tuned for narrow layout
    x_icon = side_margin_pct + 3.5
    x_code = side_margin_pct + 11
    x_text = side_margin_pct + 11  # description under code for narrow width

    # Starting Y
    y = 100 - top_margin_pct - header_height_pct
    row_step = row_height_pct

    # Helper: text wrapping for narrow column
    import textwrap
    MAX_DESC_CHARS_PER_LINE = 42  # tune for your typical description length
    TEXT_LINE_SPACING = 1.35

    def draw_wrapped_text(ax, x, y, text, fontsize=8.5, color='#222222', weight='bold', max_chars=42):
        lines = []
        for para in text.splitlines():
            wrapped = textwrap.wrap(para, width=max_chars) if para else [""]
            lines.extend(wrapped)
        # Draw lines; y is the baseline for the first line
        line_y = y
        for i, line in enumerate(lines):
            ax.text(x, line_y, line, fontsize=fontsize, ha='left', va='center',
                    color=color, weight=weight)
            line_y -= TEXT_LINE_SPACING  # move down per line
        # return total lines drawn for spacing decisions
        return len(lines)

    # Category-local numbering like on map
    category_incident_counts = {k: 0 for k in category_counts.keys()}

    # Render incidents
    for idx, inc in enumerate(categorized_incidents):
        category = inc['category']
        cat_code = category['code']
        category_incident_counts[cat_code] += 1
        count_in_category = category_incident_counts[cat_code]

        description = inc.get('description', 'No description')
        lat = inc.get('latitude', 0.0)
        lon = inc.get('longitude', 0.0)
        lat_prefix = 'N' if lat >= 0 else 'S'
        lon_prefix = 'E' if lon >= 0 else 'W'
        coord_text = f"({lat_prefix}{abs(lat):.6f}°, {lon_prefix}{abs(lon):.6f}°)"

        # Build a bold header line (category code) and a wrapped description line below
        header_text = f"{category['code']}"
        full_text = f"{description} - {coord_text}"

        # Icon: diamond (wider but not taller - use ellipse approach)
        symbol_width = 3.2   # Wider
        symbol_height = 2.0  # Keep height same
        edge = darken_color(category['color'], factor=0.6)

        # Create wider diamond using transforms
        from matplotlib.patches import Polygon as MPLPolygon
        # Diamond points (centered at origin, then will transform)
        diamond_points = np.array([
            [symbol_width, 0],      # Right point (wider)
            [0, symbol_height],     # Top point
            [-symbol_width, 0],     # Left point (wider)
            [0, -symbol_height]     # Bottom point
        ])
        # Shift to position
        diamond_points += np.array([x_icon, y])

        diamond = MPLPolygon(
            diamond_points,
            closed=True,
            facecolor=category['color'],
            edgecolor=edge,
            linewidth=1.6,
            zorder=2
        )
        ax.add_patch(diamond)

        # Number inside diamond
        ax.text(x_icon, y, str(count_in_category),
                fontsize=8.5, weight='bold', ha='center', va='center', color='#000000', zorder=3)

        # Category code (bold) - MOVED UP for more space between code and description
        code_y = y + 1.5  # Move code UP (positive direction)
        ax.text(x_code, code_y, header_text,
                fontsize=10.5, weight='bold', ha='left', va='center', color=category['color'])

        # Description stays at original position (more space from code now)
        desc_y = y - 1.1  # Description position unchanged
        lines_drawn = draw_wrapped_text(
            ax, x_text, desc_y, full_text,
            fontsize=8.5, color='#222222', weight='bold', max_chars=MAX_DESC_CHARS_PER_LINE
        )

        # Advance y by row height plus extra for wrapped lines
        extra_for_wrap = max(0, (lines_drawn - 1) * TEXT_LINE_SPACING)
        y -= (row_step + extra_for_wrap)

    # Divider before category summary
    divider_y = bottom_margin_pct + footer_block_pct - 6
    ax.plot([side_margin_pct, 100 - side_margin_pct], [divider_y, divider_y],
            color='#cfcfcf', linewidth=0.8, zorder=1)

    # Categories summary - VERTICAL LIST (one category per line)
    ax.text(side_margin_pct, divider_y - 2.4,
            'Categories', fontsize=10.5, weight='bold', ha='left', va='top', color='#111111')

    summary_items = []
    for cat_key, cat_info in category_counts.items():
        category = cat_info['category']
        count = cat_info['count']
        summary_items.append((category['code'], category['name'], count, category['color']))
    summary_items.sort(key=lambda t: t[0])  # by code

    # Vertical list layout (1 column)
    start_x = side_margin_pct
    start_y = divider_y - 5.2
    line_height = 3.5  # Space between each category

    for i, (code, name, count, color) in enumerate(summary_items):
        sx = start_x
        sy = start_y - (i * line_height)

        # diamond swatch
        swatch = RegularPolygon(
            (sx, sy),
            numVertices=4,
            radius=1.0,
            orientation=np.deg2rad(45),
            facecolor=color,
            edgecolor=darken_color(color, factor=0.6),
            linewidth=1.2,
        )
        ax.add_patch(swatch)

        ax.text(sx + 3.0, sy, f"{code}: {name} ({count})",
                fontsize=8.8, ha='left', va='center', color='#222222', weight='bold')

    # Save
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.tight_layout()
    plt.savefig(output_path, dpi=dpi, bbox_inches='tight', facecolor='white')
    plt.close()

    print(f"   ✅ Legend saved: {output_path}")
    print(f"   📊 {num_incidents} incidents across {len(category_counts)} categories")
    return output_path


# ============================================================================
# MAP GENERATOR CLASS
# ============================================================================

class MapGenerator:
    """Vector map generator using shapefiles"""

    def __init__(self, global_assets_dir:str, shapefile_dir: str, project_data: Dict[str, Any],
                 incidents: List[Dict[str, Any]]):
        """Initialize map generator"""
        self.shapefile_dir = Path(shapefile_dir)
        self.global_assets_dir = Path(global_assets_dir)
        self.project = project_data
        self.incidents = incidents

        # Setup basemap cache directory with SHORT path to avoid Windows 260 char limit
        # Use C:\tilecache instead of long nested path
        self.cache_dir = Path('C:/tilecache')
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Get pipeline identifier for cache naming - use first 8 chars only for shorter paths
        pipeline_id_full = project_data.get('_id') or project_data.get('id') or 'default'
        if hasattr(pipeline_id_full, '__str__'):
            pipeline_id_full = str(pipeline_id_full)
        # Use only first 8 characters to keep path short
        self.pipeline_id = pipeline_id_full[:8] if len(pipeline_id_full) > 8 else pipeline_id_full

        # Resolve pipeline asset path from selected asset ID
        pipeline_path = self._resolve_pipeline_asset_path(project_data)

        # shapefile_dir now points directly to the shps folder (../assets/shps)
        base = Path(shapefile_dir)
        self.shapefiles = {
            'pipeline_obama_brass': pipeline_path,  # Dynamic based on selected asset
            'settlements': base / 'BAYELSA_SETTLEMENT.geojson',
            'rivers': base / 'Bayelsa_Rivers.geojson',
            'minor_rivers': base / 'MINOR_RIVER84.geojson',
            'rivers_poly': base / 'Bayelsa_Riverspoly.geojson',
            'boundaries': base / 'LGA_BOUNDARY_84.geojson',
            'operation_base': base / 'OPERATION_BASE84.geojson',
        }

        print(f"📁 GeoJSON/Shapefile files configured from: {base}")
        print(f"🛢️  Pipeline asset: {pipeline_path}")
        print(f"💾 Basemap cache directory: {self.cache_dir}")
        print(f"🔑 Pipeline ID: {self.pipeline_id}")

    def _resolve_pipeline_asset_path(self, project_data: Dict[str, Any]) -> Path:
        """Resolve pipeline asset path from selected asset ID"""
        # Get selected pipeline asset ID
        asset_id = project_data.get('selectedPipelineAssetId')
        asset_name = project_data.get('pipelineRowShapefile', '')

        if not asset_id:
            # Fallback to legacy filename-based lookup
            legacy_filename = project_data.get('pipelineRowShapefile', '')
            if legacy_filename:
                print(f"⚠️  Using legacy filename lookup: {legacy_filename}")
                # Try to find in assets folder
                legacy_path = self.shapefile_dir / legacy_filename
                if legacy_path.exists():
                    return legacy_path

            # Ultimate fallback to hardcoded default
            print(f"⚠️  No pipeline selected, using default: Santababra-FLB_AITEO_Trunk_Line.geojson")
            return self.shapefile_dir / 'Santababra-FLB_AITEO_Trunk_Line.geojson'

        # For now, use the default pipeline
        # TODO: Fix async database lookup in sync context

        asset_path = self.global_assets_dir / asset_id / 'original' / asset_name

        print(f"   🔑 Resolved pipeline asset path: {asset_path}")
        return asset_path

    def _setup_basemap_cache(self, map_type='overview'):
        """Configure contextily to use pipeline-specific cache directory"""
        # Create cache path for this specific pipeline and map type
        pipeline_cache = self.cache_dir / self.pipeline_id / map_type
        pipeline_cache.mkdir(parents=True, exist_ok=True)

        # Convert to absolute path to avoid relative path issues
        pipeline_cache_abs = pipeline_cache.resolve()

        # Pre-create contextily's internal subdirectories to avoid race conditions
        # This prevents joblib cache warnings about missing directories
        contextily_dirs = [
            pipeline_cache_abs / 'contextily',
            pipeline_cache_abs / 'contextily' / 'tile',
            pipeline_cache_abs / 'contextily' / 'tile' / '_fetch_tile'
        ]
        for dir_path in contextily_dirs:
            dir_path.mkdir(parents=True, exist_ok=True)

        # Set contextily cache directory using absolute path
        ctx.set_cache_dir(str(pipeline_cache_abs))

        print(f"   💾 Using basemap cache: {pipeline_cache_abs}")
        return pipeline_cache_abs

    def _load_shapefiles(self):
        """Load all required shapefiles"""
        try:
            pipeline_gdf = gpd.read_file(self.shapefiles['pipeline_obama_brass'], crs="EPSG:4326")
            print(pipeline_gdf.crs)
            # settlements_gdf = gpd.read_file(self.shapefiles['settlements'])
            # rivers_gdf = gpd.read_file(self.shapefiles['rivers'])
            # minor_rivers_gdf = gpd.read_file(self.shapefiles['minor_rivers'])
            # rivers_poly_gdf = gpd.read_file(self.shapefiles['rivers_poly'])
            # boundaries_gdf = gpd.read_file(self.shapefiles['boundaries'])
            # operation_base_gdf = gpd.read_file(self.shapefiles['operation_base'])

            print(f"   ✅ Loaded {len(pipeline_gdf)} pipeline features")
            # print(f"   ✅ Loaded {len(settlements_gdf)} settlements")
            # print(f"   ✅ Loaded {len(rivers_gdf)} rivers")
            # print(f"   ✅ Loaded {len(boundaries_gdf)} boundaries")
            # print(f"   ✅ Loaded {len(operation_base_gdf)} operation bases")

            return {
                'pipeline': pipeline_gdf,
                # 'settlements': settlements_gdf,
                # 'rivers': rivers_gdf,
                # 'minor_rivers': minor_rivers_gdf,
                # 'rivers_poly': rivers_poly_gdf,
                # 'boundaries': boundaries_gdf,
                # 'operation_base': operation_base_gdf
            }
        except Exception as e:
            print(f"   ❌ Error loading shapefiles: {e}")
            raise

    def _create_incidents_gdf(self):
        """Create GeoDataFrame from incidents list"""
        if not self.incidents:
            return None

        incidents_data = []
        for inc in self.incidents:
            lat = inc['latitude']
            lon = inc['longitude']
            print(f"   📍 Incident {inc.get('incidentId', 'INC')}: lat={lat}, lon={lon}")
            incidents_data.append({
                'geometry': Point(lon, lat),  # Point takes (x, y) = (longitude, latitude)
                'id': inc.get('incidentId', 'INC'),
                'description': inc['description']
            })
        incidents_gdf = gpd.GeoDataFrame(incidents_data, crs="EPSG:4326")
        print(f"   ✅ Created {len(incidents_gdf)} incident points in EPSG:4326")
        return incidents_gdf

    def _ensure_crs(self, gdfs: dict, target_crs: str):
        """Ensure all GeoDataFrames are in target CRS"""
        for name, gdf in gdfs.items():
            if gdf is not None and gdf.crs.to_string() != target_crs:
                print(f"   🔄 Converting {name} to {target_crs}")
                gdfs[name] = gdf.to_crs(target_crs)
        return gdfs

    def _calculate_map_extent(self, pipeline_gdf, is_web_mercator=False, incidents_gdf=None):
        """Calculate map extent with FIXED aspect ratio - zoom adjusts to fit pipeline AND incidents"""
        # Start with pipeline bounds
        overall_bounds = pipeline_gdf.total_bounds

        # If we have incidents, expand bounds to include them
        if incidents_gdf is not None and len(incidents_gdf) > 0:
            incident_bounds = incidents_gdf.total_bounds
            overall_bounds = [
                min(overall_bounds[0], incident_bounds[0]),  # xmin
                min(overall_bounds[1], incident_bounds[1]),  # ymin
                max(overall_bounds[2], incident_bounds[2]),  # xmax
                max(overall_bounds[3], incident_bounds[3])   # ymax
            ]
            print(f"   📍 Expanded map extent to include {len(incidents_gdf)} incidents")

        # Get combined bounds
        data_width = overall_bounds[2] - overall_bounds[0]
        data_height = overall_bounds[3] - overall_bounds[1]

        # Calculate center point
        center_x = (overall_bounds[0] + overall_bounds[2]) / 2
        center_y = (overall_bounds[1] + overall_bounds[3]) / 2

        # Add buffer to pipeline bounds (20% on each side)
        buffer_pct = 0.20
        buffered_width = data_width * (1 + 2 * buffer_pct)
        buffered_height = data_height * (1 + 2 * buffer_pct)

        # Calculate required dimensions to maintain FIXED aspect ratio
        # The map always has the same aspect ratio, we just zoom in/out
        if buffered_height / buffered_width > TARGET_ASPECT_RATIO:
            # Pipeline is taller - fit to height
            map_height = buffered_height
            map_width = map_height / TARGET_ASPECT_RATIO
        else:
            # Pipeline is wider - fit to width
            map_width = buffered_width
            map_height = map_width * TARGET_ASPECT_RATIO

        # Calculate extent centered on pipeline
        map_extent = {
            'xmin': center_x - map_width / 2,
            'xmax': center_x + map_width / 2,
            'ymin': center_y - map_height / 2,
            'ymax': center_y + map_height / 2
        }

        unit = "m" if is_web_mercator else "°"
        print(f"   📏 Fixed Map Extent: {map_width:.4f}{unit} × {map_height:.4f}{unit} (aspect: {map_height/map_width:.3f})")
        print(f"   📏 Pipeline Size: {data_width:.4f}{unit} × {data_height:.4f}{unit}")

        return map_extent, map_width, map_height

    def _calculate_sizes(self, map_width, map_height, is_web_mercator=False):
        """Calculate all marker and symbol sizes"""
        if is_web_mercator:
            meters_per_unit = 1
        else:
            lat_center = 0  # Will be calculated from extent
            meters_per_unit = 111320 * math.cos(math.radians(lat_center))

        return {
            'pipeline_marker_radius': map_width * PIPELINE_MARKER_RADIUS_PCT,
            'incident_marker_radius': map_width * INCIDENT_MARKER_RADIUS_PCT,
            'settlement_marker_size': (map_width * SETTLEMENT_MARKER_SIZE_PCT) ** 2,
            'text_offset_x': map_width * TEXT_OFFSET_X_PCT,
            'callout_offset_x': map_width * CALLOUT_OFFSET_X_PCT,
            'callout_offset_y': map_width * CALLOUT_OFFSET_Y_PCT,
            'arrow_height': map_height * 0.05,
            'arrow_x_offset': map_width * 0.03,
            'arrow_y_offset': map_height * 0.12,
            'meters_per_unit': meters_per_unit,
        }

    def _render_base_layers(self, ax, gdfs, map_extent):
        """Render base map layers (boundaries, water, rivers)"""
        gdfs['boundaries'].plot(ax=ax, facecolor=COLORS['boundaries_fill'],
                                linewidth=BOUNDARY_LINEWIDTH, zorder=1)
        print("   ✅ LGA boundaries rendered")

        gdfs['rivers_poly'].plot(ax=ax, color=COLORS['water_polygon'], 
                                linewidth=RIVER_POLY_LINEWIDTH, zorder=2)
        print("   ✅ River polygons rendered")

        gdfs['rivers'].plot(ax=ax, color=COLORS['river_lines'], 
                           linewidth=RIVER_LINE_LINEWIDTH, zorder=2)
        gdfs['minor_rivers'].plot(ax=ax, color=COLORS['river_lines'], 
                                 linewidth=MINOR_RIVER_LINEWIDTH, zorder=2)
        print("   ✅ River lines rendered")

    def _render_settlements(self, ax, settlements_gdf, map_extent, map_width, sizes):
        """Render settlement points and labels"""
        if settlements_gdf is None or len(settlements_gdf) == 0:
            return

        map_boundary = box(map_extent['xmin'], map_extent['ymin'],
                          map_extent['xmax'], map_extent['ymax'])
        settlements_clipped = settlements_gdf[settlements_gdf.intersects(map_boundary)]

        if len(settlements_clipped) > 0:
            settlements_clipped.plot(
                ax=ax, color='#4A4A4A', markersize=sizes['settlement_marker_size'],
                marker='o', zorder=4, alpha=0.8
            )

        name_field = None
        for field in ['NAME', 'name', 'NAME_ENG', 'SETTLEMENT', 'settlement_name']:
            if field in settlements_gdf.columns:
                name_field = field
                break

        if name_field:
            potential_labels = []
            for _, row in settlements_gdf.iterrows():
                name = row.get(name_field, '')
                if not name or not isinstance(name, str) or len(name) == 0:
                    continue

                point = row.geometry.centroid if hasattr(row.geometry, 'centroid') else row.geometry

                if not (map_extent['xmin'] <= point.x <= map_extent['xmax'] and
                        map_extent['ymin'] <= point.y <= map_extent['ymax']):
                    continue

                boundary_margin = map_width * BOUNDARY_MARGIN_PCT
                if (point.x < map_extent['xmin'] + boundary_margin or
                    point.x > map_extent['xmax'] - boundary_margin or
                    point.y < map_extent['ymin'] + boundary_margin or
                    point.y > map_extent['ymax'] - boundary_margin):
                    continue

                potential_labels.append({
                    'name': name.title(),
                    'x': point.x,
                    'y': point.y,
                    'priority': len(name)
                })

            potential_labels.sort(key=lambda x: x['priority'], reverse=True)
            placed_labels = []
            min_label_distance = map_width * MIN_LABEL_DISTANCE_PCT

            for label in potential_labels:
                overlaps = False
                for placed in placed_labels:
                    dx = label['x'] - placed['x']
                    dy = label['y'] - placed['y']
                    distance = (dx**2 + dy**2)**0.5
                    if distance < min_label_distance:
                        overlaps = True
                        break

                if not overlaps:
                    ax.text(
                        label['x'],
                        label['y'] + sizes['text_offset_x'] * SETTLEMENT_LABEL_OFFSET_MULTIPLIER,
                        label['name'],
                        fontsize=SETTLEMENT_LABEL_FONTSIZE,
                        weight='normal',
                        ha='center',
                        va='bottom',
                        color=COLORS['settlement_label'],
                        family='sans-serif',
                        style='italic',
                        zorder=4
                    )
                    placed_labels.append(label)

            print(f"   ✅ {len(placed_labels)} settlements labeled")

    def _render_operation_bases(self, ax, operation_base_gdf, map_extent, map_width, label_color="#1A1A1A"):
        """Render operation base hexagons with labels"""
        if operation_base_gdf is None or len(operation_base_gdf) == 0:
            return

        map_boundary = box(map_extent['xmin'], map_extent['ymin'],
                          map_extent['xmax'], map_extent['ymax'])
        operation_base_clipped = operation_base_gdf[operation_base_gdf.intersects(map_boundary)]

        if len(operation_base_clipped) == 0:
            return

        hexagon_radius = map_width * OPERATION_BASE_HEXAGON_RADIUS_PCT
        name_field = None
        for field in ['NAME', 'name', 'NAME_ENG', 'OPERATION_BASE', 'base_name']:
            if field in operation_base_clipped.columns:
                name_field = field
                break

        for _, row in operation_base_clipped.iterrows():
            point = row.geometry.centroid if hasattr(row.geometry, 'centroid') else row.geometry

            hexagon = RegularPolygon(
                (point.x, point.y),
                numVertices=6,
                radius=hexagon_radius,
                orientation=0,
                facecolor="#FFFFFF",
                edgecolor='#000000',
                linewidth=1,
                zorder=7
            )
            ax.add_patch(hexagon)

            if name_field:
                name = row.get(name_field, '')
                if name and isinstance(name, str) and len(name) > 0:
                    ax.text(
                        point.x, point.y, "B",
                        fontsize=OPERATION_BASE_LABEL_FONTSIZE,
                        weight='bold',
                        ha='center',
                        va='center',
                        color="black",
                        zorder=8
                    )

                    ax.text(
                        point.x + map_width * OPERATION_BASE_LABEL_OFFSET_PCT,
                        point.y,
                        name.upper(),
                        fontsize=OPERATION_BASE_LABEL_FONTSIZE,
                        weight='bold',
                        ha='left',
                        va='center',
                        color=label_color,
                        family=FONT_FAMILY,
                        zorder=7
                    )

        print(f"   ✅ {len(operation_base_clipped)} operation bases rendered")

    def _render_pipeline(self, ax, pipeline_gdf, map_width):
        """Render pipeline with markers"""
        pipeline_gdf.plot(
            ax=ax,
            color=COLORS['pipeline'],
            linewidth=PIPELINE_LINEWIDTH,
            zorder=5
        )

        node_size = map_width * PIPELINE_MARKER_RADIUS_PCT * 3
        marker_coords = []

        for geom in pipeline_gdf.geometry:
            if geom.geom_type == 'LineString':
                line = geom
            elif geom.geom_type == 'MultiLineString':
                line = max(geom.geoms, key=lambda x: x.length)
            else:
                continue

            marker_distance = map_width * PIPELINE_MARKER_SPACING_PCT
            total_length = line.length
            num_markers = int(total_length / marker_distance)

            for i in range(num_markers + 1):
                distance = i * marker_distance
                if distance <= total_length:
                    point = line.interpolate(distance)
                    marker_coords.append((point.x, point.y))

        for coord in marker_coords:
            square = Rectangle(
                (coord[0] - node_size, coord[1] - node_size),
                width=node_size * 2,
                height=node_size * 2,
                facecolor=COLORS['pipeline_markers'],
                edgecolor=COLORS['pipeline_markers'],
                linewidth=PIPELINE_MARKER_LINEWIDTH,
                zorder=6
            )
            ax.add_patch(square)

        print(f"   ✅ Pipeline rendered with {len(marker_coords)} markers")
        return marker_coords

    def _render_pipeline_label(self, ax, pipeline_gdf, map_width):
        """Render pipeline label along the route"""
        pipeline_name = "OBAMA-BRASS RoW"

        if 'Name' in pipeline_gdf.columns:
            pipeline_name = pipeline_gdf.iloc[0]['Name']
        elif 'NAME' in pipeline_gdf.columns:
            pipeline_name = pipeline_gdf.iloc[0]['NAME']

        if pipeline_name and isinstance(pipeline_name, str):
            pipeline_name = pipeline_name.strip()
        else:
            pipeline_name = "OBAMA-BRASS RoW"

        for geom in pipeline_gdf.geometry:
            if geom.geom_type == 'LineString':
                line = geom
            elif geom.geom_type == 'MultiLineString':
                line = max(geom.geoms, key=lambda x: x.length)
            else:
                continue

            total_length = line.length
            distance = total_length * PIPELINE_LABEL_POSITION_FRACTION
            point = line.interpolate(distance)

            sample_dist = total_length * PIPELINE_LABEL_ANGLE_SAMPLE_PCT
            point_before = line.interpolate(max(0, distance - sample_dist))
            point_after = line.interpolate(min(total_length, distance + sample_dist))

            dx = point_after.x - point_before.x
            dy = point_after.y - point_before.y
            angle = np.degrees(np.arctan2(dy, dx))

            if angle > 90:
                angle -= 180
            elif angle < -90:
                angle += 180

            angle_rad = np.radians(angle)
            perp_angle = angle_rad + np.pi / 2
            offset_distance = map_width * PIPELINE_LABEL_OFFSET_PCT

            offset_x = point.x + offset_distance * np.cos(perp_angle)
            offset_y = point.y + offset_distance * np.sin(perp_angle)

            display_name = pipeline_name.upper()
            if len(display_name) > PIPELINE_LABEL_MAX_LENGTH:
                display_name = display_name[:PIPELINE_LABEL_MAX_LENGTH-3] + '...'

            label_fontsize = PIPELINE_LABEL_FONTSIZE_LONG if len(display_name) > 20 else PIPELINE_LABEL_FONTSIZE

            ax.text(
                offset_x, offset_y, display_name,
                fontsize=label_fontsize,
                weight='bold',
                ha='center',
                va='center',
                color='#000000',
                rotation=angle,
                rotation_mode='anchor',
                zorder=7
            )

        print(f"   ✅ Pipeline label added: {pipeline_name}")

    def _render_incidents(self, ax, incidents_gdf, sizes, map_width=None, pipeline_gdf=None, show_callouts=True):
        """Render color-coded incident markers with optional count callout labels"""
        if incidents_gdf is None or len(incidents_gdf) == 0:
            return

        incident_categories = {}
        for idx, incident in enumerate(incidents_gdf.itertuples()):
            desc = incident.description if hasattr(incident, 'description') else f"Incident {idx + 1}"
            category = categorize_incident(desc)
            cat_code = category['code']

            if cat_code not in incident_categories:
                incident_categories[cat_code] = {
                    'category': category,
                    'incidents': []
                }
            incident_categories[cat_code]['incidents'].append((idx, incident))

        # Calculate callout offset distance in map coordinates (only if showing callouts)
        if show_callouts:
            if map_width:
                offset_distance = map_width * 0.12  # Increased from 10% to 12%
            else:
                offset_distance = 0.015  # Increased fallback
        else:
            offset_distance = 0  # No callouts needed

        # Helper function to check if two line segments intersect
        def lines_intersect(p1, p2, p3, p4):
            """Check if line segment p1-p2 intersects with p3-p4"""
            def ccw(A, B, C):
                return (C[1] - A[1]) * (B[0] - A[0]) > (B[1] - A[1]) * (C[0] - A[0])

            return ccw(p1, p3, p4) != ccw(p2, p3, p4) and ccw(p1, p2, p3) != ccw(p1, p2, p4)

        # Track placed callout arrows (start, end) to avoid crossings
        placed_arrows = []

        # Minimum distance between callouts (increased to prevent line crossings)
        min_callout_distance = offset_distance * 0.6  # Increased from 0.4

        # Position callouts at various angles
        angle_positions = [45, 135, 225, 315, 90, 180, 270, 0, 60, 120, 240, 300]
        incident_index = 0

        for cat_code, cat_data in incident_categories.items():
            category = cat_data['category']
            incidents_in_category = cat_data['incidents']

            for count_in_category, (idx, incident) in enumerate(incidents_in_category, start=1):
                x, y = incident.geometry.x, incident.geometry.y

                outline_color = darken_color(category['color'], factor=0.6)

                # Draw incident marker circle
                circle = Circle(
                    (x, y),
                    radius=sizes['incident_marker_radius'],
                    facecolor=category['color'],
                    edgecolor=outline_color,
                    linewidth=INCIDENT_MARKER_LINEWIDTH,
                    zorder=10,
                    alpha=0.7
                )
                ax.add_patch(circle)

                # Only render callouts if requested (skip for satellite maps with composite layout)
                if show_callouts:
                    # Find best callout position avoiding overlaps, pipeline, and line crossings
                    callout_x, callout_y = None, None
                    best_angle = None

                    # Try multiple angles to find non-overlapping position
                    for angle_offset in range(0, len(angle_positions)):
                        angle_idx = (incident_index + angle_offset) % len(angle_positions)
                        angle = angle_positions[angle_idx]
                        angle_rad = np.radians(angle)

                        test_x = x + offset_distance * np.cos(angle_rad)
                        test_y = y + offset_distance * np.sin(angle_rad)

                        # Check distance from other callouts
                        too_close = False
                        for (px, py) in placed_arrows:
                            distance = np.sqrt((test_x - px[0])**2 + (test_y - py[0])**2)
                            if distance < min_callout_distance:
                                too_close = True
                                break

                        # Check if this arrow would cross any existing arrows
                        if not too_close:
                            test_arrow = ((x, y), (test_x, test_y))
                            for existing_arrow in placed_arrows:
                                if lines_intersect(test_arrow[0], test_arrow[1],
                                                 existing_arrow[0], existing_arrow[1]):
                                    too_close = True
                                    break

                        # Check distance from pipeline if provided
                        if not too_close and pipeline_gdf is not None:
                            try:
                                from shapely.geometry import Point
                                callout_point = Point(test_x, test_y)
                                min_pipeline_distance = offset_distance * 0.3

                                for geom in pipeline_gdf.geometry:
                                    if callout_point.distance(geom) < min_pipeline_distance:
                                        too_close = True
                                        break
                            except:
                                pass  # Skip pipeline check if error

                        if not too_close:
                            callout_x = test_x
                            callout_y = test_y
                            best_angle = angle
                            break

                    # Fallback if no good position found
                    if callout_x is None:
                        angle = angle_positions[incident_index % len(angle_positions)]
                        angle_rad = np.radians(angle)
                        callout_x = x + offset_distance * np.cos(angle_rad)
                        callout_y = y + offset_distance * np.sin(angle_rad)

                    # Track this arrow to prevent future crossings
                    placed_arrows.append(((x, y), (callout_x, callout_y)))

                    # Create callout label
                    callout_label = f"{cat_code}-{count_in_category}"

                    # Draw callout circle
                    ax.text(
                        callout_x, callout_y, callout_label,
                        fontsize=12,
                        weight='bold',
                        ha='center',
                        va='center',
                        color='black',
                        bbox=dict(
                            boxstyle='circle,pad=0.7',
                            facecolor='white',
                            edgecolor='black',
                            linewidth=2.0,
                            alpha=0.95
                        ),
                        zorder=12
                    )

                    # Draw arrow from incident to callout
                    ax.annotate('',
                               xy=(callout_x, callout_y),
                               xytext=(x, y),
                               arrowprops=dict(
                                   arrowstyle='->',
                                   color='black',
                                   lw=1.5,
                                   shrinkA=sizes['incident_marker_radius'] * 1.2,
                                   shrinkB=15
                               ),
                               zorder=11)

                incident_index += 1

        if show_callouts:
            print(f"   ✅ {len(incidents_gdf)} incident markers rendered with callouts ({len(incident_categories)} categories)")
        else:
            print(f"   ✅ {len(incidents_gdf)} incident markers rendered without callouts ({len(incident_categories)} categories)")

    def _add_north_arrow_and_scale(self, ax, map_extent, map_width, map_height, sizes, color):
        """Add north arrow and scale bar"""
        # shapefile_dir is ../assets/shps, logos are in ../assets/logos
        logo_dir = self.shapefile_dir.parent / 'logos'
        north_arrow_path = logo_dir / 'north-arrow.png'

        if not north_arrow_path.exists():
            print(f"   ⚠️  North arrow not found")
            return

        try:
            from matplotlib.offsetbox import OffsetImage, AnnotationBbox
            import matplotlib.image as mpimg

            arrow_img = mpimg.imread(str(north_arrow_path))

            # Apply color filter based on the color parameter while preserving transparency
            if color == 'white':
                # Check if image has alpha channel (RGBA)
                if arrow_img.shape[-1] == 4:
                    # Invert only RGB channels, keep alpha channel unchanged
                    arrow_img[:, :, :3] = 1 - arrow_img[:, :, :3]
                else:
                    # If no alpha channel, just invert
                    arrow_img = 1 - arrow_img

            margin_x = map_width * ARROW_MARGIN_PCT
            margin_y = map_height * ARROW_MARGIN_PCT

            arrow_x = map_extent['xmin'] + margin_x
            arrow_y = map_extent['ymin'] + margin_y

            arrow_size_inches = ARROW_SIZE_PX / DPI
            zoom = arrow_size_inches / (100 / DPI)

            imagebox = OffsetImage(arrow_img, zoom=zoom)
            ab = AnnotationBbox(
                imagebox, (arrow_x, arrow_y),
                frameon=False,
                box_alignment=(0, 0),
                zorder=20
            )
            ax.add_artist(ab)

            arrow_width = arrow_size_inches / PAGE_WIDTH_INCHES * map_width
            scale_x_start = arrow_x + arrow_width * ARROW_WIDTH_MULTIPLIER
            scale_y = arrow_y

            scale_length = (SCALE_BAR_TARGET_KM * 1000) / sizes['meters_per_unit']

            # Use the color parameter for the scale bar line
            ax.plot([scale_x_start, scale_x_start + scale_length], [scale_y, scale_y],
                color=color, linewidth=3, solid_capstyle='butt', zorder=20)

            tick_height = map_height * SCALE_BAR_TICK_HEIGHT_PCT
            # Use the color parameter for the tick marks
            ax.plot([scale_x_start, scale_x_start], 
                [scale_y - tick_height, scale_y + tick_height],
                color=color, linewidth=2, zorder=20)
            ax.plot([scale_x_start + scale_length, scale_x_start + scale_length],
                [scale_y - tick_height, scale_y + tick_height],
                color=color, linewidth=2, zorder=20)

            # Use the color parameter for the text
            ax.text(scale_x_start + scale_length/2, scale_y + tick_height * 2.5,
                f'0        {SCALE_BAR_TARGET_KM/2:.1f}        {SCALE_BAR_TARGET_KM} Km',
                fontsize=7, ha='center', weight='normal', color=color, zorder=20)

            print(f"   ✅ North arrow and scale bar added")

        except Exception as e:
            print(f"   ⚠️  Failed to add north arrow: {e}")

    def generate_incident_legend_map(self, output_path: str) -> str:
        """Generate a standalone incident legend (4" × 14")"""
        print(f"📋 Generating incident legend map...")

        incidents_gdf = self._create_incidents_gdf()
        if incidents_gdf is None or len(incidents_gdf) == 0:
            print(f"   ⚠️  No incidents to create legend")
            return None

        # Convert to WGS84 for lat/lon display
        if incidents_gdf.crs.to_string() != "EPSG:4326":
            incidents_gdf = incidents_gdf.to_crs("EPSG:4326")

        # Categorize incidents
        incident_categories = {}
        for _, incident in incidents_gdf.iterrows():
            category = categorize_incident(incident.get('description', ''))
            cat_code = category['code']
            if cat_code not in incident_categories:
                incident_categories[cat_code] = {'category': category, 'incidents': []}
            incident_categories[cat_code]['incidents'].append(incident)

        # Create figure (7.2" × 14" - wider for better readability)
        fig, ax = plt.subplots(figsize=(7.2, 14), dpi=300)
        ax.set_xlim(0, 100)
        ax.set_ylim(0, 194.4)  # 100 * (14/7.2) to keep circles circular
        ax.axis('off')
        fig.patch.set_facecolor('white')

        # Legend title
        ax.text(50, 186, 'INCIDENT LEGEND', fontsize=20, weight='bold', ha='center', va='top', color='#1a1a1a')
        ax.plot([8, 92], [178, 178], color='#cccccc', linewidth=2)

        # Content positioning
        entry_y = 168
        category_spacing = 10.5
        line_spacing = 5.8
        incident_spacing = 7
        between_category_spacing = 12

        # Text wrapping helper
        import textwrap

        # Iterate through categories (sorted by frequency)
        for cat_code, cat_data in sorted(incident_categories.items(), key=lambda x: len(x[1]['incidents']), reverse=True):
            category = cat_data['category']
            incidents = cat_data['incidents']

            # Category circle
            ax.add_patch(Circle((10, entry_y), radius=3.5, facecolor=category['color'], edgecolor='#333333', linewidth=1.5))

            # Category name and count (fontsize 16 - minimum)
            ax.text(18, entry_y, f"{category['name']} ({len(incidents)})", fontsize=16, weight='bold',
                   ha='left', va='center', color='#1a1a1a', family='sans-serif')
            entry_y -= category_spacing

            # List incidents
            for idx, incident in enumerate(incidents, start=1):
                lat = incident.geometry.y
                lon = incident.geometry.x
                description = incident.get('description', 'No description')

                # Incident code and coordinates on same line (fontsize 16 - minimum)
                ax.text(20, entry_y, f"{cat_code}-{idx}:", fontsize=16, weight='bold',
                       ha='left', va='top', color='#444444', family='sans-serif')
                ax.text(38, entry_y, f"({lat:.6f}°, {lon:.6f}°)", fontsize=16,
                       style='italic', ha='left', va='top', color='#666666', family='sans-serif')
                entry_y -= line_spacing

                # Description with wrapping (fontsize 16 - minimum size)
                wrapped_desc = textwrap.wrap(description, width=48)
                for desc_line in wrapped_desc:
                    ax.text(20, entry_y, desc_line, fontsize=16, ha='left', va='top',
                           color='#333333', family='sans-serif')
                    entry_y -= line_spacing

                entry_y -= incident_spacing

            entry_y -= between_category_spacing

        # Footer
        ax.text(50, 7, f'Total Incidents: {len(incidents_gdf)}', fontsize=16, weight='bold', ha='center', va='bottom', color='#1a1a1a')

        # Save
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        plt.tight_layout(pad=0)
        plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
        plt.close()

        print(f"   ✅ Legend saved: {output_path}")
        print(f"   📊 {len(incident_categories)} categories, {len(incidents_gdf)} total incidents")
        return output_path

    def generate_overview_map(self, output_path: str) -> str:
        """
        Generate overview map with vector layers and a beautiful tile basemap.
        Basemap is added LAST to prevent arrow rendering issues.
        """
        print(f"🗺️  Generating overview map...")

        # 1. Load shapefiles
        gdfs = self._load_shapefiles()
        incidents_gdf = self._create_incidents_gdf()

        # 2. Ensure all in Web Mercator (EPSG:3857)
        target_crs = "EPSG:3857"
        gdfs = self._ensure_crs(gdfs, target_crs)
        if incidents_gdf is not None:
            incidents_gdf = incidents_gdf.to_crs(target_crs)

        # 3. Calculate map extent (in Meters) - INCLUDE INCIDENTS
        map_extent, map_width, map_height = self._calculate_map_extent(
            gdfs['pipeline'], is_web_mercator=True, incidents_gdf=incidents_gdf
        )

        # 4. Calculate sizes
        sizes = self._calculate_sizes(map_width, map_height)
        sizes['meters_per_unit'] = 1  # Web Mercator uses meters

        # 5. Create figure
        fig, ax = plt.subplots(figsize=(PAGE_WIDTH_INCHES, PAGE_HEIGHT_INCHES), dpi=DPI)
        fig.patch.set_facecolor('white')
        ax.set_aspect('equal')

        print(f"   📐 Figure: {PAGE_WIDTH_INCHES}\" × {PAGE_HEIGHT_INCHES}\" @ {DPI} DPI")

        # 6. Set extent FIRST
        ax.set_xlim(map_extent['xmin'], map_extent['xmax'])
        ax.set_ylim(map_extent['ymin'], map_extent['ymax'])

        # 7. Render vector layers (BEFORE basemap to avoid arrow rendering issues)
        # self._render_settlements(ax, gdfs['settlements'], map_extent, map_width, sizes)
        # self._render_operation_bases(ax, gdfs['operation_base'], map_extent, map_width)
        self._render_pipeline(ax, gdfs['pipeline'], map_width)
        # self._render_pipeline_label(ax, gdfs['pipeline'], map_width)
        self._render_incidents(ax, incidents_gdf, sizes, map_width, pipeline_gdf=gdfs['pipeline'])

        # 8. Add scale bar and north arrow
        self._add_north_arrow_and_scale(ax, map_extent, map_width, map_height, sizes, color="#1A1A1A")

        # 9. Setup basemap cache for this pipeline
        self._setup_basemap_cache(map_type='overview')

        # 10. Add basemap LAST (after adjust_text completes)
        # This prevents basemap transform from interfering with arrow rendering
        print("   🌍 Downloading and stitching basemap tiles...")
        print("   ⏱️  Timeout: 1 minute for primary, 30 seconds for fallback")

        try:
            import threading

            # Try primary basemap (OpenStreetMap) with timeout
            basemap_loaded = [False]
            error_msg = [None]

            def load_basemap_osm():
                try:
                    ctx.add_basemap(
                        ax,
                        crs=gdfs['pipeline'].crs.to_string(),
                        source=ctx.providers.OpenStreetMap.Mapnik,
                        zoom='auto',
                        attribution=False,
                        alpha=1.0,
                        zorder=0
                    )
                    basemap_loaded[0] = True
                except Exception as e:
                    error_msg[0] = str(e)

            # Start basemap loading in a thread with 1 minute timeout
            thread = threading.Thread(target=load_basemap_osm, daemon=True)
            thread.start()
            thread.join(timeout=1)  # 1 minute timeout

            if basemap_loaded[0]:
                print("   ✅ OpenStreetMap basemap loaded successfully")
            else:
                # Try lighter CartoDB basemap as fallback
                if error_msg[0]:
                    print(f"   ⚠️ Primary basemap failed: {error_msg[0]}")
                else:
                    print(f"   ⚠️ Primary basemap timed out after 1 minute")

                print("   🔄 Trying lighter CartoDB basemap...")
                basemap_loaded[0] = False
                error_msg[0] = None

                def load_basemap_cartodb():
                    try:
                        ctx.add_basemap(
                            ax,
                            crs=gdfs['pipeline'].crs.to_string(),
                            source=ctx.providers.CartoDB.Positron,
                            zoom='auto',
                            attribution=False,
                            alpha=1.0,
                            zorder=0
                        )
                        basemap_loaded[0] = True
                    except Exception as e:
                        error_msg[0] = str(e)

                # Try CartoDB with 30 second timeout
                thread2 = threading.Thread(target=load_basemap_cartodb, daemon=True)
                thread2.start()
                thread2.join(timeout=30)  # 30 second timeout for lighter basemap

                if basemap_loaded[0]:
                    print("   ✅ CartoDB basemap loaded successfully")
                else:
                    if error_msg[0]:
                        print(f"   ⚠️ Fallback basemap also failed: {error_msg[0]}")
                    else:
                        print(f"   ⚠️ Fallback basemap timed out after 30 seconds")
                    print(f"   ℹ️  Continuing without basemap tiles...")

        except Exception as e:
            print(f"   ⚠️ Warning: Could not load basemap: {e}")
            print(f"   ℹ️  Continuing without basemap tiles...")

        # 10. Final setup
        ax.set_axis_off()

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        plt.tight_layout(pad=0)
        plt.savefig(output_path, dpi=DPI, bbox_inches='tight',
                    facecolor='white', edgecolor='none')
        plt.close()

        print(f"   ✅ Map saved: {output_path}")
        return output_path

    # def generate_satellite_overview_map(self, output_path: str) -> str:
    #     """Generate satellite overview map (EXACT SAME dimensions/extent as overview map, but with satellite basemap)"""
    #     print(f"🛰️  Generating satellite overview map...")

    #     # Load shapefiles
    #     gdfs = self._load_shapefiles()
    #     incidents_gdf = self._create_incidents_gdf()
    #     print(len(incidents_gdf))

    #     # Use WGS84 (degrees) - SAME coordinate system as overview map
    #     target_crs = "EPSG:4326"
    #     gdfs = self._ensure_crs(gdfs, target_crs)
    #     if incidents_gdf is not None:
    #         incidents_gdf = incidents_gdf.to_crs(target_crs)

    #     print(f"   ℹ️  Using WGS84 (degrees) - SAME as overview map")

    #     # Calculate map extent - SAME method as overview map - INCLUDE INCIDENTS
    #     map_extent, map_width, map_height = self._calculate_map_extent(
    #         gdfs['pipeline'], is_web_mercator=False, incidents_gdf=incidents_gdf
    #     )

    #     # Calculate sizes - SAME method as overview map
    #     sizes = self._calculate_sizes(map_width, map_height, is_web_mercator=False)

    #     # Create figure - EXACT SAME as overview map
    #     fig, ax = plt.subplots(figsize=(PAGE_WIDTH_INCHES, PAGE_HEIGHT_INCHES), dpi=DPI)
    #     ax.set_aspect('equal')

    #     # Set extent BEFORE adding basemap - EXACT SAME as overview map
    #     ax.set_xlim(map_extent['xmin'], map_extent['xmax'])
    #     ax.set_ylim(map_extent['ymin'], map_extent['ymax'])

    #     print(f"   📐 Figure: {PAGE_WIDTH_INCHES}\" × {PAGE_HEIGHT_INCHES}\" @ {DPI} DPI")
    #     print(f"   📐 Extent: X [{map_extent['xmin']:.6f}°, {map_extent['xmax']:.6f}°]")
    #     print(f"   📐 Extent: Y [{map_extent['ymin']:.6f}°, {map_extent['ymax']:.6f}°]")

    #     # Render vector layers first
    #     self._render_pipeline(ax, gdfs['pipeline'], map_width)
    #     self._render_incidents(ax, incidents_gdf, sizes, map_width, pipeline_gdf=gdfs['pipeline'])
    #     self._render_operation_bases(ax, gdfs['operation_base'], map_extent, map_width, label_color="#FFFFFF")
    #     self._add_north_arrow_and_scale(ax, map_extent, map_width, map_height, sizes, color="#1a1a1a")

    #     # Setup basemap cache for this pipeline
    #     self._setup_basemap_cache(map_type='satellite')

    #     # Add satellite basemap LAST with timeout
    #     print(f"   📡 Fetching satellite imagery (zoom={SATELLITE_ZOOM_LEVEL})...")
    #     print("   ⏱️  Timeout: 1 minute for satellite, 30 seconds for fallback")

    #     try:
    #         import threading
    #         import time

    #         basemap_loaded = [False]
    #         error_msg = [None]
    #         start_time = time.time()

    #         def load_satellite_basemap():
    #             try:
    #                 ctx.add_basemap(
    #                     ax,
    #                     source=ESRI_SATELLITE_URL,
    #                     zoom=SATELLITE_ZOOM_LEVEL,
    #                     crs='EPSG:4326',
    #                     attribution=False,
    #                     zorder=0
    #                 )
    #                 basemap_loaded[0] = True
    #             except Exception as e:
    #                 error_msg[0] = str(e)

    #         # Try satellite basemap with 1 minute timeout
    #         thread = threading.Thread(target=load_satellite_basemap, daemon=True)
    #         thread.start()
    #         thread.join(timeout=60)  # 1 minute timeout

    #         if basemap_loaded[0]:
    #             elapsed = time.time() - start_time
    #             print(f"   ✅ Satellite imagery loaded in {elapsed:.1f}s")
    #         else:
    #             # Try lighter CartoDB as fallback
    #             if error_msg[0]:
    #                 print(f"   ⚠️ Satellite basemap failed: {error_msg[0]}")
    #             else:
    #                 print(f"   ⚠️ Satellite basemap timed out after 1 minute")

    #             print("   🔄 Trying lighter CartoDB basemap...")
    #             basemap_loaded[0] = False
    #             error_msg[0] = None

    #             def load_basemap_cartodb():
    #                 try:
    #                     ctx.add_basemap(
    #                         ax,
    #                         source=ctx.providers.CartoDB.Positron,
    #                         zoom='auto',
    #                         crs='EPSG:4326',
    #                         attribution=False,
    #                         alpha=1.0,
    #                         zorder=0
    #                     )
    #                     basemap_loaded[0] = True
    #                 except Exception as e:
    #                     error_msg[0] = str(e)

    #             # Try CartoDB with 30 second timeout
    #             thread2 = threading.Thread(target=load_basemap_cartodb, daemon=True)
    #             thread2.start()
    #             thread2.join(timeout=30)  # 30 second timeout

    #             if basemap_loaded[0]:
    #                 print("   ✅ CartoDB fallback basemap loaded successfully")
    #             else:
    #                 if error_msg[0]:
    #                     print(f"   ⚠️ Fallback basemap also failed: {error_msg[0]}")
    #                 else:
    #                     print(f"   ⚠️ Fallback basemap timed out after 30 seconds")
    #                 print(f"   ℹ️  Continuing without basemap tiles...")

    #     except Exception as e:
    #         print(f"   ⚠️ Warning: Could not load satellite basemap: {e}")
    #         print(f"   ℹ️  Continuing without basemap tiles...")

    #     # Set extent and save - EXACT SAME as overview map
    #     ax.set_axis_off()
    #     ax.set_xlim(map_extent['xmin'], map_extent['xmax'])
    #     ax.set_ylim(map_extent['ymin'], map_extent['ymax'])

    #     os.makedirs(os.path.dirname(output_path), exist_ok=True)
    #     plt.tight_layout(pad=0)
    #     plt.savefig(output_path, dpi=DPI, bbox_inches='tight',
    #                facecolor='white', edgecolor='none')
    #     plt.close()

    #     print(f"   ✅ Satellite map saved: {output_path}")
    #     return output_path


    def generate_satellite_overview_map(self, output_path: str) -> tuple[list[str], list[list[dict]]]:
        """
        Generates multiple satellite overview maps.
        1. Calculates categories for all incidents.
        2. Sorts them by category.
        3. Paginates them (max 3 per map).

        Returns:
            tuple: (list of map paths, list of incident groups with metadata)
        """
        INCIDENTS_PER_MAP = 3
        print(f"🛰️  Starting categorized multi-map generation (Max {INCIDENTS_PER_MAP} incidents/map)...")
        print("!!!!!!!!!!!!!!", output_path)
        # 1. Load data ONCE
        gdfs = self._load_shapefiles()
        all_incidents_gdf = self._create_incidents_gdf()

        # Handle case with no incidents
        if all_incidents_gdf is None or len(all_incidents_gdf) == 0:
            print("ℹ️ No incidents found. Generating one base map.")
            output_path = os.path.join(output_path, 'satellite_overview_base.png')
            map_path = self._generate_single_satellite_map(gdfs, None, output_path)
            return ([map_path], [[]])

        # ---------------------------------------------------------
        # 2. ENRICH & SORT: Apply categorization manually to allow sorting
        # ---------------------------------------------------------
        print("ℹ️ Categorizing incidents for sorting...")
        
        # We create a temporary list to hold the category codes
        cat_codes = []
        
        for desc in all_incidents_gdf['description']:
            # We use the SAME function your _render_incidents uses
            # Assuming 'categorize_incident' is available in this scope
            cat_data = categorize_incident(desc) 
            cat_codes.append(cat_data['code'])

        # Assign this list as a new column in the GeoDataFrame
        all_incidents_gdf['incident_category'] = cat_codes

        # NOW we can sort by this new column
        all_incidents_gdf = all_incidents_gdf.sort_values(
            by='incident_category', ascending=True
        ).reset_index(drop=True)


        # incident_dict = {inc.get('incidentId'): inc for inc in self.incidents}

    # # Rebuild self.incidents in the new sorted order
    #     sorted_incidents = []
    #     for _, row in all_incidents_gdf.iterrows():
    #         inc_id = row.get("incidentId")
    #         if inc_id in incident_dict:
    #             sorted_incidents.append(incident_dict[inc_id])
    #         else:
    #             print(f"⚠️ Warning: incidentId {inc_id} not found in self.incidents")

    #     self.incidents = sorted_incidents  # REPLACE the old list

        # 3. Calculate pagination
        num_incidents = len(all_incidents_gdf)
        num_maps = (num_incidents + INCIDENTS_PER_MAP - 1) // INCIDENTS_PER_MAP
        
        print(f"ℹ️ Found {num_incidents} incidents across categories: {all_incidents_gdf['incident_category'].unique()}")
        print(f"ℹ️ Will generate {num_maps} map(s).")

        output_paths = []
        incident_groups = []  # Store incident metadata for each map

        # 4. Loop to generate maps
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!", self.incidents)
        for i in range(num_maps):
            start_index = i * INCIDENTS_PER_MAP
            end_index = start_index + INCIDENTS_PER_MAP

            # Slice the specific subset of incidents for this map
            incidents_subset_gdf = all_incidents_gdf.iloc[start_index:end_index]

            # Extract incident metadata (photoPath, circleCenter, lat/lon) for this group
            incidents_metadata = []
            for idx in range(start_index, min(end_index, len(self.incidents))):
                row = all_incidents_gdf.iloc[idx]   # Fixed: use idx not i

                print("!!!!!!!!", row)
                # Find this incident in your original list by incidentId
                incident = next(
                    (inc for inc in self.incidents if inc.get("incidentId") == row["id"]),
                    None
                )

                print("!!!!!!!!", incident)

                if incident is None:
                    print(f"⚠️ incidentId {row['incidentId']} not found in metadata list")
                    continue

                metadata = {
                    'incidentId': incident.get('incidentId', ''),
                    'description': incident.get('description', ''),
                    'latitude': incident.get('latitude', 0),
                    'longitude': incident.get('longitude', 0),
                    'photoPath': incident.get('photoPath', ''),
                    'circleCenter': incident.get('circleCenter', {}),
                    'status': incident.get('status', ''),
                }
                incidents_metadata.append(metadata)

            incident_groups.append(incidents_metadata)
            print(f"📸 Attached {len(incidents_metadata)} incident metadata for map {i+1}")

            # Generate a filename based on the category of the first incident in this batch
            try:
                # We can now safely use the column we just created
                cat_label = incidents_subset_gdf['incident_category'].iloc[0]
                # Clean the string for filename safety
                cat_label = "".join([c if c.isalnum() else "_" for c in str(cat_label)])
            except:
                cat_label = "Uncategorized"

            filename = f"Map_{i+1:02d}_{cat_label}.png"
            subset_output_path = os.path.join(output_path, filename)
            print(subset_output_path)

            # Call the helper to generate the composite image (map + annotated images + lines)
            map_path = self._generate_composite_satellite_map(
                gdfs, incidents_subset_gdf, incidents_metadata, subset_output_path
            )
            output_paths.append(map_path)
            print("!!!!!!!!!!! finsih creating one map")

        print(f"✅ Finished generating all {len(output_paths)} maps with incident metadata.")
        return (output_paths, incident_groups)



    def _generate_composite_satellite_map(self, gdfs, incidents_gdf, incidents_metadata, output_path):
        """
        Generates a composite image with:
        - 70% left: Satellite map with incident markers
        - 30% right: Annotated incident images (up to 3) stacked vertically
        - Connector lines from incident markers to circle centers in annotated images
        """
        from PIL import Image, ImageDraw
        from pathlib import Path
        import tempfile

        print(f"   🎨 Creating composite satellite overview with annotated images...")

        # Step 1: Generate the satellite map to a temporary file and get its extent
        temp_map = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
        temp_map.close()
        map_image_path, map_extent = self._generate_single_satellite_map(gdfs, incidents_gdf, temp_map.name)

        # Step 2: Load the map image
        map_img = Image.open(map_image_path)
        map_width, map_height = map_img.size
        print(f"   📏 Map dimensions: {map_width}x{map_height}")

        # Step 3: Calculate composite dimensions
        # Map takes 70% of width, images take 30%
        composite_width = int(map_width / 0.7)  # If map is 70%, calculate total width
        images_column_width = composite_width - map_width
        composite_height = map_height
        print(f"   📐 Composite dimensions: {composite_width}x{composite_height}")
        print(f"   📦 Images column width: {images_column_width}")

        # Step 4: Create composite canvas
        composite = Image.new('RGB', (composite_width, composite_height), color='white')
        composite.paste(map_img, (0, 0))
        print(f"   ✅ Map pasted at (0, 0)")

        # Step 5: Get base projects directory for loading annotated images
        # Navigate from app/services/ -> app/ -> Backend/report system/ -> projects/
        base_dir = Path(__file__).resolve().parents[2] / "projects"

        # Step 6: Add annotated images and draw connector lines
        draw = ImageDraw.Draw(composite)

        # Use the map extent calculated by _generate_single_satellite_map (includes proper buffering)
        if incidents_gdf is not None and len(incidents_gdf) > 0:
            map_extent_lon_min = map_extent['xmin']
            map_extent_lon_max = map_extent['xmax']
            map_extent_lat_min = map_extent['ymin']
            map_extent_lat_max = map_extent['ymax']

            print(f"   📍 Using map extent: lon [{map_extent_lon_min:.6f}, {map_extent_lon_max:.6f}] lat [{map_extent_lat_min:.6f}, {map_extent_lat_max:.6f}]")

            if map_extent_lon_max > map_extent_lon_min and map_extent_lat_max > map_extent_lat_min:

                # Process each incident
                num_incidents = min(len(incidents_metadata), 3)
                image_height = composite_height // 3  # Divide into 3 equal rows
                padding = 10

                for idx, incident in enumerate(incidents_metadata[:3]):
                    photo_path_relative = incident.get('photoPath', '')
                    print("!!!!!!!!!!!!", photo_path_relative)
                    circle_center = incident.get('circleCenter', {})
                    inc_lat = incident.get('latitude', 0)
                    inc_lon = incident.get('longitude', 0)
                    inc_description = incident.get('description', '')

                    # Get category color for this incident
                    category = categorize_incident(inc_description)
                    incident_color = category['color']  # This is a hex string like '#FF5733'
                    # Convert hex color to RGB tuple for PIL
                    color_rgb = tuple(int(incident_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
                    print(f"      🎨 Incident category: {category['name']}, Color: {incident_color} -> RGB{color_rgb}")

                    if not photo_path_relative:
                        print(f"      ⚠️ No photo path for incident {idx + 1}")
                        continue

                    # Construct full path
                    photo_path = str(base_dir / photo_path_relative)

                    if not os.path.exists(photo_path):
                        print(f"      ⚠️ Image not found: {photo_path}")
                        continue

                    try:
                        # Load and crop annotated image to square
                        annotated_img = Image.open(photo_path)

                        # Convert to RGB if necessary (handles RGBA, CMYK, grayscale, etc.)
                        if annotated_img.mode != 'RGB':
                            print(f"      🔄 Converting image from {annotated_img.mode} to RGB")
                            annotated_img = annotated_img.convert('RGB')

                        orig_width, orig_height = annotated_img.size
                        print(f"      📐 Original image size: {orig_width}x{orig_height}")

                        # Get circle center - clamp to image bounds if coordinates are from different resolution
                        circle_x = circle_center.get('x', orig_width / 2)
                        circle_y = circle_center.get('y', orig_height / 2)

                        # If circle center is outside image bounds, use center of image
                        if circle_x < 0 or circle_x > orig_width or circle_y < 0 or circle_y > orig_height:
                            print(f"      ⚠️ Circle center ({circle_x:.0f}, {circle_y:.0f}) outside image bounds ({orig_width}x{orig_height}), using image center")
                            circle_x = orig_width / 2
                            circle_y = orig_height / 2

                        print(f"      🎯 Circle center: ({circle_x:.0f}, {circle_y:.0f})")

                        # Crop to square around circle - use the whole image if it's already small
                        padding_factor = 1.8
                        estimated_diameter = min(orig_width, orig_height) / 2
                        square_size = int(estimated_diameter * padding_factor)

                        # Ensure minimum square size
                        square_size = max(square_size, 100)

                        left = int(circle_x - square_size / 2)
                        top = int(circle_y - square_size / 2)
                        right = left + square_size
                        bottom = top + square_size

                        # Clamp to image bounds
                        left = max(0, left)
                        top = max(0, top)
                        right = min(orig_width, right)
                        bottom = min(orig_height, bottom)

                        # Ensure we have a valid crop area
                        crop_width = right - left
                        crop_height = bottom - top

                        if crop_width <= 0 or crop_height <= 0:
                            print(f"      ⚠️ Invalid crop dimensions, using full image")
                            left, top, right, bottom = 0, 0, orig_width, orig_height
                            crop_size = min(orig_width, orig_height)
                        else:
                            # Make it square using the smaller dimension
                            crop_size = min(crop_width, crop_height)

                            # Adjust crop to be square, centered on circle
                            if crop_width > crop_height:
                                # Wider than tall, adjust horizontally
                                center_x = (left + right) / 2
                                left = int(center_x - crop_size / 2)
                                right = left + crop_size
                                left = max(0, left)
                                right = min(orig_width, right)
                                if right - left < crop_size:
                                    crop_size = right - left
                            else:
                                # Taller than wide, adjust vertically
                                center_y = (top + bottom) / 2
                                top = int(center_y - crop_size / 2)
                                bottom = top + crop_size
                                top = max(0, top)
                                bottom = min(orig_height, bottom)
                                if bottom - top < crop_size:
                                    crop_size = bottom - top

                        print(f"      ✂️  Crop box: ({left}, {top}, {right}, {bottom}) size={crop_size}")

                        cropped = annotated_img.crop((left, top, right, bottom))

                        # Resize to fit in column - maintain SQUARE aspect ratio
                        # Use the smaller of width/height to ensure it fits
                        max_size = min(images_column_width - 2 * padding, image_height - 2 * padding)
                        target_size = (max_size, max_size)  # Square!
                        print(f"      📏 Resizing to SQUARE: {target_size}")
                        cropped_resized = cropped.resize(target_size, Image.Resampling.LANCZOS)

                        # Paste into composite - center it in the row
                        paste_x = map_width + padding
                        paste_y = idx * image_height + padding + (image_height - max_size) // 2  # Center vertically in row
                        print(f"      📍 Pasting at: ({paste_x}, {paste_y})")
                        composite.paste(cropped_resized, (paste_x, paste_y))

                        # Calculate circle center position in composite
                        circle_x_in_crop = circle_x - left
                        circle_y_in_crop = circle_y - top

                        # Debug: check if circle is within crop
                        if circle_x_in_crop < 0 or circle_x_in_crop > (right - left) or circle_y_in_crop < 0 or circle_y_in_crop > (bottom - top):
                            print(f"      ⚠️ Circle center outside crop region, using crop center")
                            circle_x_in_crop = (right - left) / 2
                            circle_y_in_crop = (bottom - top) / 2

                        print(f"      📍 Circle in crop: ({circle_x_in_crop:.1f}, {circle_y_in_crop:.1f})")

                        scale_x = target_size[0] / crop_size if crop_size > 0 else 1
                        scale_y = target_size[1] / crop_size if crop_size > 0 else 1

                        circle_center_x = paste_x + (circle_x_in_crop * scale_x)
                        circle_center_y = paste_y + (circle_y_in_crop * scale_y)

                        print(f"      🎯 Final circle center in composite: ({circle_center_x:.1f}, {circle_center_y:.1f})")

                        # Calculate incident marker position on map
                        print(f"      🔍 Calculating connector line for incident {idx + 1}")
                        print(f"         Map extent check: lon [{map_extent_lon_min:.6f}, {map_extent_lon_max:.6f}] lat [{map_extent_lat_min:.6f}, {map_extent_lat_max:.6f}]")
                        print(f"         Incident position: lat={inc_lat:.6f}, lon={inc_lon:.6f}")

                        if map_extent_lon_max > map_extent_lon_min and map_extent_lat_max > map_extent_lat_min:
                            norm_x = (inc_lon - map_extent_lon_min) / (map_extent_lon_max - map_extent_lon_min)
                            norm_y = 1 - ((inc_lat - map_extent_lat_min) / (map_extent_lat_max - map_extent_lat_min))

                            incident_map_x = norm_x * map_width
                            incident_map_y = norm_y * map_height

                            print(f"         Normalized: x={norm_x:.3f}, y={norm_y:.3f}")
                            print(f"         Incident marker at: ({incident_map_x:.1f}, {incident_map_y:.1f})")
                            print(f"         Circle center at: ({circle_center_x:.1f}, {circle_center_y:.1f})")

                            # Draw connector line using incident's category color
                            draw.line(
                                [(incident_map_x, incident_map_y), (circle_center_x, circle_center_y)],
                                fill=(255, 0, 0),  # Use category color
                                width=8
                            )

                            print(f"      ✅ Added incident {idx + 1} with connector line (color: {incident_color})")
                        else:
                            print(f"      ⚠️ Skipping connector: Invalid map extent")

                    except Exception as e:
                        print(f"      ⚠️ Error processing incident {idx + 1}: {e}")

        # Step 7: Save composite image
        composite.save(output_path, format='PNG', dpi=(DPI, DPI))
        print(f"   ✅ Composite saved: {os.path.basename(output_path)}")

        # Cleanup temp map
        try:
            os.unlink(map_image_path)
        except:
            pass

        return output_path

    def _generate_single_satellite_map(self, gdfs, incidents_gdf, output_path):
        """
        Helper: Renders a single map for a specific subset of incidents.
        Contains the original threading/rendering logic.
        """
        print(f"   📍 Processing map: {os.path.basename(output_path)}")
        
        # Use WGS84 (degrees)
        target_crs = "EPSG:4326"
        gdfs = self._ensure_crs(gdfs, target_crs)
        
        if incidents_gdf is not None:
            incidents_gdf = incidents_gdf.to_crs(target_crs)

        # Calculate map extent based on THIS SUBSET of incidents
        map_extent, map_width, map_height = self._calculate_map_extent(
            gdfs['pipeline'], is_web_mercator=False, incidents_gdf=incidents_gdf
        )

        # Calculate sizes
        sizes = self._calculate_sizes(map_width, map_height, is_web_mercator=False)

        # Create figure
        fig, ax = plt.subplots(figsize=(PAGE_WIDTH_INCHES, PAGE_HEIGHT_INCHES), dpi=DPI)
        ax.set_aspect('equal')

        # Set extent BEFORE adding basemap
        ax.set_xlim(map_extent['xmin'], map_extent['xmax'])
        ax.set_ylim(map_extent['ymin'], map_extent['ymax'])

        # Render vector layers first
        self._render_pipeline(ax, gdfs['pipeline'], map_width)
        if incidents_gdf is not None:
            # Render incidents WITHOUT callouts for satellite maps (connectors will be added in composite)
            self._render_incidents(ax, incidents_gdf, sizes, map_width, pipeline_gdf=gdfs['pipeline'], show_callouts=False)
        # self._render_operation_bases(ax, gdfs['operation_base'], map_extent, map_width, label_color="#FFFFFF")
        self._add_north_arrow_and_scale(ax, map_extent, map_width, map_height, sizes, color="#1a1a1a")

        # Setup basemap cache
        self._setup_basemap_cache(map_type='satellite')

        # --- ORIGINAL THREADING LOGIC PRESERVED ---
        print(f"    📡 Fetching satellite imagery...")
        try:
            import threading
            import time

            basemap_loaded = [False]
            error_msg = [None]
            start_time = time.time()

            def load_satellite_basemap():
                try:
                    ctx.add_basemap(
                        ax,
                        source=ESRI_SATELLITE_URL,
                        zoom=SATELLITE_ZOOM_LEVEL,
                        crs='EPSG:4326',
                        attribution=False,
                        zorder=0
                    )
                    basemap_loaded[0] = True
                except Exception as e:
                    error_msg[0] = str(e)

            # Try satellite basemap with 1 minute timeout
            thread = threading.Thread(target=load_satellite_basemap, daemon=True)
            thread.start()
            thread.join(timeout=60) 

            if basemap_loaded[0]:
                elapsed = time.time() - start_time
                print(f"    ✅ Satellite imagery loaded in {elapsed:.1f}s")
            else:
                if error_msg[0]:
                    print(f"    ⚠️ Satellite basemap failed: {error_msg[0]}")
                else:
                    print(f"    ⚠️ Satellite basemap timed out")

                print("    🔄 Trying lighter CartoDB basemap...")
                basemap_loaded[0] = False
                error_msg[0] = None

                def load_basemap_cartodb():
                    try:
                        ctx.add_basemap(
                            ax,
                            source=ctx.providers.CartoDB.Positron,
                            zoom='auto',
                            crs='EPSG:4326',
                            attribution=False,
                            alpha=1.0,
                            zorder=0
                        )
                        basemap_loaded[0] = True
                    except Exception as e:
                        error_msg[0] = str(e)

                # Try CartoDB with 30 second timeout
                thread2 = threading.Thread(target=load_basemap_cartodb, daemon=True)
                thread2.start()
                thread2.join(timeout=30) 

                if basemap_loaded[0]:
                    print("    ✅ CartoDB fallback basemap loaded")
                else:
                    print(f"    ⚠️ Fallback basemap failed/timed out")
                    print(f"    ℹ️  Continuing without basemap tiles...")

        except Exception as e:
            print(f"    ⚠️ Warning: Could not load satellite basemap: {e}")
        # -------------------------------------------

        # Set extent and save
        ax.set_axis_off()
        ax.set_xlim(map_extent['xmin'], map_extent['xmax'])
        ax.set_ylim(map_extent['ymin'], map_extent['ymax'])

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        plt.tight_layout(pad=0)
        plt.savefig(output_path, dpi=DPI, bbox_inches='tight',
                    facecolor='white', edgecolor='none')
        plt.close()

        print(f"    ✅ Saved: {output_path}")
        return output_path, map_extent

# ============================================================================
# ASYNC WRAPPER
# ============================================================================

async def generate_overview_map(global_assets_dir: str, shapefile_dir: str, project_data: Dict[str, Any],
                                incidents: List[Dict[str, Any]], output_path: str) -> str:
    """Generate overview map (async wrapper)"""
    generator = MapGenerator(global_assets_dir, shapefile_dir, project_data, incidents)
    return generator.generate_overview_map(output_path)