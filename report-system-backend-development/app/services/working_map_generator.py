"""
Map Generator Service

Generates vector-based GIS maps using shapefiles.
Based on the working POC from python-poc/generate_vector_map_poc.py
"""

import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch
from matplotlib import patheffects
from shapely.geometry import Point
from typing import List, Dict, Any, Tuple
from pathlib import Path
import os
import numpy as np
import math
import contextily as ctx

# PHASE 1: Exact color palette from ArcMap reference (experimental.md)
COLORS = {
    'background': '#D4E8DE',        # Slightly different seafoam green
    'water_polygon': '#00C5FF',     # rgb(0,197,255) - Bright cyan for sea/wide rivers
    'river_lines': '#00C5FF',       # rgb(0,197,255) - Same bright cyan for river lines
    'boundaries': '#9B9B9B',        # Lighter gray for LGA boundaries
    'boundaries_fill': '#D9FCD6',   # rgb(217,252,214) - Light green fill for LGA polygons
    'pipeline': '#FF00C5',          # rgb(255,0,197) - Pink/Magenta for pipeline line
    'pipeline_markers': '#FF00C5',  # rgb(255,0,197) - Same color for markers
    'incident_marker': '#FF0000',   # Red
    'incident_outline': '#FFFFFF',  # White
    'callout_bg': '#FFFFE0',        # Light yellow / ivory for callout box
    'callout_border': '#000000',    # Black
    'text_main': '#000000',         # Black for most text
    'settlement_label': '#000000',  # Black for settlement labels (from shapefile)
}


class MapGenerator:
    """Vector map generator using shapefiles"""

    def __init__(self, shapefile_dir: str, project_data: Dict[str, Any],
                 incidents: List[Dict[str, Any]]):
        """
        Initialize map generator

        Args:
            shapefile_dir: Directory containing shapefiles
            project_data: Project metadata
            incidents: List of incidents with lat/lng
        """
        self.shapefile_dir = Path(shapefile_dir)
        self.project = project_data
        self.incidents = incidents

        # Exact shapefiles used for ArcMap-style map generation
        # Note: shapefile_dir already points to the shape-file directory
        base = Path(shapefile_dir)
        self.shapefiles = {
            # PIPELINE SHAPEFILES - Adding Obama-Brass only for now
            'pipeline_obama_brass': base / 'Shapefile source/KOJOSAM_shapefiles/KOJOSAM/OBAMA-BRASS_RoW.shp',
            # 'pipeline_tebidaba_brass': base / 'Shapefile source/KOJOSAM_shapefiles/KOJOSAM/TEBIDABA-BRASS_RoW.shp',

            # BASE LAYERS
            'settlements': base / 'Bayelsa-settlement/BAYELSA_SETTLEMENT.shp',
            'rivers': base / 'Bayelsa-rivers/Bayelsa_Rivers.shp',
            'minor_rivers': base / 'Minor-River84/MINOR_RIVER84.shp',
            'rivers_poly': base / 'Bayelsa-rivers/Bayelsa_Riverspoly.shp',
            'sea': base / 'Sea-84/SEA_84.shp',
            'boundaries': base / 'LGA-boundary/LGA_BOUNDARY_84.shp',
            # 'operation_base': base / 'Operation-base/OPERATION_BASE84.shp',
        }

        print(f"📁 Shapefiles configured:")
        print(f"   - shapefile_dir received: {shapefile_dir}")
        print(f"   - base Path object: {base}")
        print(f"   - Pipeline (Obama-Brass): OBAMA-BRASS_RoW")
        print(f"   - Settlements: BAYELSA_SETTLEMENT")
        print(f"   - Rivers: Bayelsa_Rivers")
        print(f"   - Minor Rivers: MINOR_RIVER84")
        print(f"   - Rivers (Poly): Bayelsa_Riverspoly")
        print(f"   - Sea: SEA_84")
        print(f"   - Boundaries: LGA_BOUNDARY_84")

    def generate_overview_map(self, output_path: str) -> str:
        """
        PHASE 2: Generate ArcMap-style overview map following experimental.md specifications

        Implements the complete Phase 2 rendering pipeline:
        - Water polygons (zorder=1)
        - LGA boundaries (zorder=2)
        - River lines (zorder=3)
        - Settlement points & labels (zorder=4)
        - Pipeline route & markers (zorder=5,6)
        - Pipeline label (zorder=7)
        - Incident callouts (zorder=8,9,10)
        - Map furniture (zorder=15)

        Returns:
            Path to generated map image
        """
        print(f"🗺️  Generating ArcMap-style overview map (PHASE 2)...")

        # ArcMap-Style Layout Configuration
        # Page size: 8.01" × 5.95" (similar to ArcMap Layout View page setup)
        PAGE_WIDTH_INCHES = 8.01
        PAGE_HEIGHT_INCHES = 5.95
        DPI = 150  # 150 for testing/screen, 300 for print quality
        MAP_SCALE = 136910  # 1:136,910 scale

        print(f"📄 Layout Configuration:")
        print(f"   - Page Size: {PAGE_WIDTH_INCHES}\" × {PAGE_HEIGHT_INCHES}\"")
        print(f"   - DPI: {DPI}")
        print(f"   - Map Scale: 1:{MAP_SCALE:,}")

        # Load BASE LAYERS + Obama-Brass Pipeline
        try:
            pipeline_obama_brass_gdf = gpd.read_file(self.shapefiles['pipeline_obama_brass'])
            settlements_gdf = gpd.read_file(self.shapefiles['settlements'])
            rivers_gdf = gpd.read_file(self.shapefiles['rivers'])
            minor_rivers_gdf = gpd.read_file(self.shapefiles['minor_rivers'])
            rivers_poly_gdf = gpd.read_file(self.shapefiles['rivers_poly'])
            sea_gdf = gpd.read_file(self.shapefiles['sea'])
            boundaries_gdf = gpd.read_file(self.shapefiles['boundaries'])

            print(f"   ✅ Loaded {len(pipeline_obama_brass_gdf)} Obama-Brass pipeline features")
            print(f"   ✅ Loaded {len(settlements_gdf)} settlement features")
            print(f"   ✅ Loaded {len(rivers_gdf)} river line features")
            print(f"   ✅ Loaded {len(minor_rivers_gdf)} minor river features")
            print(f"   ✅ Loaded {len(rivers_poly_gdf)} river polygon features")
            print(f"   ✅ Loaded {len(sea_gdf)} sea features")
            print(f"   ✅ Loaded {len(boundaries_gdf)} boundary features")

        except Exception as e:
            print(f"   ❌ Error loading shapefiles: {e}")
            import traceback
            traceback.print_exc()
            raise

        # Create incidents GeoDataFrame
        if self.incidents:
            incidents_data = []
            for inc in self.incidents:
                incidents_data.append({
                    'geometry': Point(inc['longitude'], inc['latitude']),
                    'id': inc.get('incidentId', 'INC'),
                    'description': inc['description']
                })
            incidents_gdf = gpd.GeoDataFrame(incidents_data, crs="EPSG:4326")
            print(f"   ✅ Created {len(incidents_gdf)} incident points")
        else:
            incidents_gdf = None

        # KEEP ALL LAYERS IN WGS84 (EPSG:4326) - DO NOT CONVERT TO UTM!
        # The original ArcMap map was created in WGS84 with decimal degrees
        # All calculations will work with degrees, not meters
        target_crs = "EPSG:4326"  # WGS84 (units: decimal degrees)
        print(f"   ✅ Keeping all layers in {target_crs} (degrees)")

        # Verify all shapefiles are in WGS84 (should already be)
        for name, gdf in [
            ('pipeline_obama_brass', pipeline_obama_brass_gdf),
            ('settlements', settlements_gdf),
            ('rivers', rivers_gdf),
            ('minor_rivers', minor_rivers_gdf),
            ('rivers_poly', rivers_poly_gdf),
            ('sea', sea_gdf),
            ('boundaries', boundaries_gdf)
        ]:
            if gdf.crs.to_epsg() != 4326:
                print(f"   🔄 Converting {name} from {gdf.crs} to EPSG:4326")
                if name == 'pipeline_obama_brass':
                    pipeline_obama_brass_gdf = pipeline_obama_brass_gdf.to_crs(target_crs)
                elif name == 'settlements':
                    settlements_gdf = settlements_gdf.to_crs(target_crs)
                elif name == 'rivers':
                    rivers_gdf = rivers_gdf.to_crs(target_crs)
                elif name == 'minor_rivers':
                    minor_rivers_gdf = minor_rivers_gdf.to_crs(target_crs)
                elif name == 'rivers_poly':
                    rivers_poly_gdf = rivers_poly_gdf.to_crs(target_crs)
                elif name == 'sea':
                    sea_gdf = sea_gdf.to_crs(target_crs)
                elif name == 'boundaries':
                    boundaries_gdf = boundaries_gdf.to_crs(target_crs)

        # Ensure incidents are also in WGS84 (they already are, created with EPSG:4326)
        if incidents_gdf is not None and incidents_gdf.crs.to_epsg() != 4326:
            incidents_gdf = incidents_gdf.to_crs(target_crs)

        # CALCULATE MAP EXTENT: Use only clean layers (rivers_poly and settlements)
        # Note: sea and rivers shapefiles have invalid global extents
        import pandas as pd
        import numpy as np

        # Use only layers with valid Bayelsa extents
        # rivers_poly and settlements have correct bounds for Bayelsa state
        # NOTE: minor_rivers extends too far (4.5° to 9.0°E), so exclude it from extent calc
        clean_bounds = []
        for gdf in [rivers_poly_gdf, settlements_gdf]:
            if not gdf.empty:
                clean_bounds.append(gdf.total_bounds)

        # Get the overall bounds [minx, miny, maxx, maxy]
        if clean_bounds:
            clean_bounds_array = np.array(clean_bounds)
            overall_bounds = [
                clean_bounds_array[:, 0].min(),  # minx
                clean_bounds_array[:, 1].min(),  # miny
                clean_bounds_array[:, 2].max(),  # maxx
                clean_bounds_array[:, 3].max()   # maxy
            ]
        else:
            # Fallback - should not reach here
            overall_bounds = rivers_poly_gdf.total_bounds

        print(f"   ℹ️  Using clean layers for extent (rivers_poly, settlements only)")
        print(f"   ℹ️  Excluded: sea, rivers (global bounds), minor_rivers (extends too far)")

        print(f"   🔍 Map extent from base layers (WGS84):")
        print(f"      Longitude: {overall_bounds[0]:.6f}° to {overall_bounds[2]:.6f}°")
        print(f"      Latitude: {overall_bounds[1]:.6f}° to {overall_bounds[3]:.6f}°")

        # Calculate extent dimensions in degrees
        width_deg = overall_bounds[2] - overall_bounds[0]
        height_deg = overall_bounds[3] - overall_bounds[1]

        # Add 5% buffer in degrees (smaller buffer for better fit)
        buffer_pct = 0.05
        buffer_x = width_deg * buffer_pct
        buffer_y = height_deg * buffer_pct

        # Calculate map extent (Data Frame extent in ArcMap terms)
        map_extent = {
            'xmin': overall_bounds[0] - buffer_x,
            'xmax': overall_bounds[2] + buffer_x,
            'ymin': overall_bounds[1] - buffer_y,
            'ymax': overall_bounds[3] + buffer_y
        }

        # Map dimensions in degrees
        map_width_deg = map_extent['xmax'] - map_extent['xmin']
        map_height_deg = map_extent['ymax'] - map_extent['ymin']

        print(f"   🎯 Map extent calculated from base layers")
        print(f"   📏 Map Extent: {map_width_deg:.4f}° × {map_height_deg:.4f}° (degrees)")

        # Calculate meters per degree at center latitude for reference
        lat_center = (map_extent['ymin'] + map_extent['ymax']) / 2
        # At equator: 1° longitude ≈ 111.32 km, 1° latitude ≈ 110.57 km
        # Adjust for latitude: longitude distance varies with cos(latitude)
        meters_per_deg_lon = 111320 * math.cos(math.radians(lat_center))
        meters_per_deg_lat = 110574  # Roughly constant

        # Approximate map size in km (for display purposes)
        map_width_km = map_width_deg * meters_per_deg_lon / 1000
        map_height_km = map_height_deg * meters_per_deg_lat / 1000
        print(f"   📏 Approximate ground extent: {map_width_km:.2f} km × {map_height_km:.2f} km")

        # Calculate all sizes as percentages of map dimensions IN DEGREES
        sizes = {
            'pipeline_marker_radius': map_width_deg * 0.002,     # 0.2% of width in degrees
            'incident_marker_radius': map_width_deg * 0.004,     # 0.4% of width in degrees
            'settlement_marker_size': (map_width_deg * 0.0005) ** 2,  # For markersize param
            'text_offset_x': map_width_deg * 0.001,              # Label offset in degrees
            'callout_offset_x': map_width_deg * 0.06,            # Callout distance in degrees
            'callout_offset_y': map_width_deg * 0.015,
            'arrow_height': map_height_deg * 0.05,               # North arrow in degrees
            'arrow_x_offset': map_width_deg * 0.03,
            'arrow_y_offset': map_height_deg * 0.12,
            'meters_per_deg_lon': meters_per_deg_lon,            # For scale bar calculation
        }

        print(f"   🎯 Pipeline marker radius: {sizes['pipeline_marker_radius']:.6f}° ({sizes['pipeline_marker_radius'] * meters_per_deg_lon:.1f} m)")
        print(f"   🎯 Incident marker radius: {sizes['incident_marker_radius']:.6f}° ({sizes['incident_marker_radius'] * meters_per_deg_lon:.1f} m)")

        # Create figure with FIXED page dimensions (ArcMap Layout View approach)
        # Unlike before, we don't calculate aspect ratio from data - we use predefined page size
        fig, ax = plt.subplots(
            figsize=(PAGE_WIDTH_INCHES, PAGE_HEIGHT_INCHES),
            dpi=DPI
        )
        ax.set_facecolor(COLORS['background'])
        fig.patch.set_facecolor('white')

        # CRITICAL: Set equal aspect for accurate representation
        ax.set_aspect('equal')

        print(f"   📐 Figure Size: {PAGE_WIDTH_INCHES}\" × {PAGE_HEIGHT_INCHES}\" @ {DPI} DPI")
        print(f"   📐 Output Resolution: {int(PAGE_WIDTH_INCHES * DPI)} × {int(PAGE_HEIGHT_INCHES * DPI)} pixels")
        print("   🎨 PHASE 2: Rendering layers per experimental.md specifications...")

        # PHASE 2: STEP 2 - Plot Base Layers (Water and Boundaries)
        # 1. Plot Water Polygons (Sea and River Polygons) - zorder=1
        sea_gdf.plot(ax=ax, color=COLORS['water_polygon'], edgecolor='none', zorder=1)
        rivers_poly_gdf.plot(ax=ax, color=COLORS['water_polygon'], edgecolor='none', zorder=1)
        print("   ✅ Step 2: Water polygons rendered (zorder=1)")

        # 2. Plot LGA Boundaries with fill - zorder=2
        boundaries_gdf.plot(ax=ax, facecolor=COLORS['boundaries_fill'],
                           edgecolor=COLORS['boundaries'],
                           linewidth=0.5, zorder=2)
        print("   ✅ Step 2: LGA boundaries rendered (zorder=2)")

        # 3. Plot River Lines - zorder=3
        rivers_gdf.plot(ax=ax, color=COLORS['river_lines'], linewidth=0.8, zorder=3)
        minor_rivers_gdf.plot(ax=ax, color=COLORS['river_lines'], linewidth=0.6, zorder=3)
        print("   ✅ Step 2: River lines rendered (zorder=3)")

        # SETTLEMENT LABELS SKIPPED - Will add later if needed
        print(f"   ⏭️  Settlement labels skipped (building incrementally)")

        # PHASE 2: STEP 4 - Plot Obama-Brass Pipeline - zorder=5
        # Using 15pt line width with dashed style (T23 Pipeline 2 approximation)
        # Color: rgb(255,0,197) = #FF00C5

        # Convert 15pt to appropriate linewidth (matplotlib uses points)
        pipeline_linewidth = 15

        # Plot pipeline with dashed line style
        # Dash pattern: (dash_length, gap_length) in points
        pipeline_obama_brass_gdf.plot(
            ax=ax,
            color=COLORS['pipeline'],
            linewidth=pipeline_linewidth,
            linestyle=(0, (10, 5)),  # Dashed: 10pt dash, 5pt gap
            zorder=5
        )
        print(f"   ✅ Step 4: Obama-Brass pipeline rendered (15pt, dashed, zorder=5)")

        # INCIDENTS REMOVED - Building base map first
        print(f"   ⏭️  Incident markers skipped (base map only)")

        # MAP FURNITURE REMOVED - Building base map first
        print(f"   ⏭️  North arrow and scale bar skipped (base map only)")
        print("   ✅ WGS84 APPROACH COMPLETE: All layers rendered in decimal degrees (test.md)!")

        # Remove axes
        ax.set_axis_off()

        # Set map extent (Data Frame extent in ArcMap)
        # No additional padding needed - buffer already applied
        ax.set_xlim(map_extent['xmin'], map_extent['xmax'])
        ax.set_ylim(map_extent['ymin'], map_extent['ymax'])

        print(f"   📐 Map Extent Set: X({map_extent['xmin']:.0f}, {map_extent['xmax']:.0f}) Y({map_extent['ymin']:.0f}, {map_extent['ymax']:.0f})")

        # Save with explicit DPI setting
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        plt.tight_layout(pad=0)
        plt.savefig(
            output_path,
            dpi=DPI,  # Use configured DPI
            bbox_inches='tight',
            facecolor='white',
            edgecolor='none'
        )
        plt.close()

        print(f"   ✅ Map saved: {output_path}")
        print(f"   📊 Output: {int(PAGE_WIDTH_INCHES * DPI)} × {int(PAGE_HEIGHT_INCHES * DPI)} pixels @ {DPI} DPI")

        return output_path

    def generate_satellite_overview_map(self, output_path: str, zoom_level: int = 13) -> str:
        """
        Generate satellite imagery overview map with pipeline overlay

        Args:
            output_path: Path to save the map
            zoom_level: Zoom level for satellite imagery (higher = more detail)

        Returns:
            Path to generated map
        """
        print(f"🛰️  Generating satellite overview map...")

        try:
            # Load pipeline shapefiles
            pipeline_obama_brass_gdf = gpd.read_file(self.shapefiles['pipeline_obama_brass'])
            pipeline_tebidaba_brass_gdf = gpd.read_file(self.shapefiles['pipeline_tebidaba_brass'])

            # Combine pipelines
            import pandas as pd
            pipeline_gdf = pd.concat([pipeline_obama_brass_gdf, pipeline_tebidaba_brass_gdf], ignore_index=True)

            # Convert to Web Mercator (required for contextily)
            pipeline_gdf_web = pipeline_gdf.to_crs(epsg=3857)

            # Create incidents GeoDataFrame
            if self.incidents:
                incidents_data = []
                for inc in self.incidents:
                    incidents_data.append({
                        'geometry': Point(inc['longitude'], inc['latitude']),
                        'id': inc.get('incidentId', 'INC'),
                        'description': inc['description']
                    })
                incidents_gdf = gpd.GeoDataFrame(incidents_data, crs="EPSG:4326")
                incidents_gdf_web = incidents_gdf.to_crs(epsg=3857)
            else:
                incidents_gdf_web = None

            # Create figure
            fig, ax = plt.subplots(figsize=(12, 14), dpi=300)

            # Plot pipeline route
            pipeline_gdf_web.plot(ax=ax, color='#FF00FF', linewidth=4,
                                 linestyle=(0, (8, 4)), alpha=0.9, zorder=5)

            # Add pipeline dots
            pipeline_coords = []
            for geom in pipeline_gdf_web.geometry:
                if hasattr(geom, 'coords'):
                    pipeline_coords.extend(list(geom.coords))

            for i, coord in enumerate(pipeline_coords[::5]):
                circle = Circle((coord[0], coord[1]), radius=150,
                               facecolor='#FF69B4', edgecolor='#FF00FF',
                               linewidth=1, alpha=1.0, zorder=6)
                ax.add_patch(circle)

            # Plot incidents
            if incidents_gdf_web is not None and len(incidents_gdf_web) > 0:
                for incident in incidents_gdf_web.itertuples():
                    x, y = incident.geometry.x, incident.geometry.y

                    # Red marker
                    circle = Circle((x, y), radius=200,
                                   facecolor='#FF0000', edgecolor='#FFFFFF',
                                   linewidth=3, alpha=1.0, zorder=10)
                    ax.add_patch(circle)

            # Add satellite basemap
            print(f"   📡 Fetching satellite imagery (zoom={zoom_level})...")
            ctx.add_basemap(ax, source=ctx.providers.Esri.WorldImagery, zoom=zoom_level)

            # Add pipeline label
            if len(pipeline_coords) > 0:
                mid_idx = len(pipeline_coords) // 2
                mid_coord = pipeline_coords[mid_idx]
                ax.text(mid_coord[0], mid_coord[1] + 500,
                       self.project.get('routeInspected', 'PIPELINE').upper(),
                       fontsize=10, weight='bold', rotation=-60,
                       ha='center', va='bottom',
                       color='white',
                       path_effects=[patheffects.withStroke(linewidth=4, foreground='black')],
                       zorder=15)

            # Add scale bar and north arrow
            bounds = pipeline_gdf_web.total_bounds

            # North arrow
            arrow_x = bounds[0] + (bounds[2] - bounds[0]) * 0.05
            arrow_y = bounds[1] + (bounds[3] - bounds[1]) * 0.08
            arrow_height = (bounds[3] - bounds[1]) * 0.05

            arrow = FancyArrowPatch((arrow_x, arrow_y), (arrow_x, arrow_y + arrow_height),
                                   arrowstyle='->', mutation_scale=30,
                                   linewidth=3, color='white',
                                   path_effects=[patheffects.withStroke(linewidth=5, foreground='black')],
                                   zorder=20)
            ax.add_patch(arrow)

            ax.text(arrow_x, arrow_y + arrow_height * 1.3, 'N',
                   fontsize=16, weight='bold', ha='center', va='center',
                   color='white',
                   path_effects=[patheffects.withStroke(linewidth=4, foreground='black')],
                   zorder=20)

            # Scale bar
            scale_x = bounds[0] + (bounds[2] - bounds[0]) * 0.05
            scale_y = bounds[1] + (bounds[3] - bounds[1]) * 0.18
            scale_length_m = 1000  # 1 km in meters (Web Mercator uses meters)

            ax.plot([scale_x, scale_x + scale_length_m], [scale_y, scale_y],
                   'w-', linewidth=5, solid_capstyle='butt',
                   path_effects=[patheffects.withStroke(linewidth=7, foreground='black')],
                   zorder=20)

            ax.text(scale_x + scale_length_m/2, scale_y + (bounds[3] - bounds[1]) * 0.02,
                   '0     0.375   0.75          1.5\nKm',
                   fontsize=9, ha='center', weight='bold',
                   color='white',
                   path_effects=[patheffects.withStroke(linewidth=3, foreground='black')],
                   zorder=20, linespacing=0.8)

            # Remove axes
            ax.set_axis_off()

            # Save
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            plt.tight_layout(pad=0)
            plt.savefig(output_path, dpi=300, bbox_inches='tight')
            plt.close()

            print(f"   ✅ Satellite map saved: {output_path}")
            return output_path

        except Exception as e:
            print(f"   ❌ Error generating satellite map: {e}")
            raise

    def generate_satellite_thumbnail(self, incident: Dict[str, Any],
                                     output_path: str, zoom_level: int = 16) -> str:
        """
        Generate zoomed-in satellite thumbnail for a specific incident

        Args:
            incident: Incident data with lat/lng
            output_path: Path to save thumbnail
            zoom_level: Zoom level (higher = more zoomed in)

        Returns:
            Path to generated thumbnail
        """
        try:
            # Load pipeline shapefiles
            pipeline_obama_brass_gdf = gpd.read_file(self.shapefiles['pipeline_obama_brass'])
            pipeline_tebidaba_brass_gdf = gpd.read_file(self.shapefiles['pipeline_tebidaba_brass'])

            # Combine pipelines
            import pandas as pd
            pipeline_gdf = pd.concat([pipeline_obama_brass_gdf, pipeline_tebidaba_brass_gdf], ignore_index=True)

            pipeline_gdf_web = pipeline_gdf.to_crs(epsg=3857)

            # Create incident point
            inc_point = Point(incident['longitude'], incident['latitude'])
            inc_gdf = gpd.GeoDataFrame([{'geometry': inc_point}], crs="EPSG:4326")
            inc_gdf_web = inc_gdf.to_crs(epsg=3857)

            # Create figure
            fig, ax = plt.subplots(figsize=(8, 8), dpi=300)

            # Plot pipeline section (if visible)
            pipeline_gdf_web.plot(ax=ax, color='#FF00FF', linewidth=6,
                                 linestyle=(0, (8, 4)), alpha=0.9, zorder=5)

            # Plot incident marker
            x, y = inc_gdf_web.geometry.iloc[0].x, inc_gdf_web.geometry.iloc[0].y
            circle = Circle((x, y), radius=80,
                           facecolor='#FF0000', edgecolor='#FFFFFF',
                           linewidth=3, alpha=1.0, zorder=10)
            ax.add_patch(circle)

            # Add satellite basemap
            ctx.add_basemap(ax, source=ctx.providers.Esri.WorldImagery, zoom=zoom_level)

            # Set bounds (zoom to incident with buffer)
            buffer_m = 500  # 500 meters buffer
            ax.set_xlim(x - buffer_m, x + buffer_m)
            ax.set_ylim(y - buffer_m, y + buffer_m)

            # Add text overlay
            pipeline_name = self.project.get('routeInspected', 'Pipeline').split()[-3:]
            pipeline_text = ' '.join(pipeline_name) + ' RoW'

            # Top-left: Pipeline name
            ax.text(0.05, 0.95, pipeline_text,
                   transform=ax.transAxes,
                   fontsize=14, weight='bold',
                   ha='left', va='top',
                   color='white',
                   bbox=dict(boxstyle='round,pad=0.5', facecolor='black', alpha=0.7),
                   zorder=20)

            # Bottom-right: Incident description
            desc_text = incident['description']
            coords_text = f"(N{incident['latitude']:.6f}, E{incident['longitude']:.6f})"

            ax.text(0.95, 0.05, f"{desc_text}\n{coords_text}",
                   transform=ax.transAxes,
                   fontsize=9, weight='bold',
                   ha='right', va='bottom',
                   color='white',
                   bbox=dict(boxstyle='round,pad=0.5', facecolor='black', alpha=0.7),
                   zorder=20, linespacing=1.4)

            # Remove axes
            ax.set_axis_off()

            # Save
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            plt.tight_layout(pad=0)
            plt.savefig(output_path, dpi=300, bbox_inches='tight')
            plt.close()

            return output_path

        except Exception as e:
            print(f"   ❌ Error generating thumbnail for incident: {e}")
            raise


async def generate_overview_map(shapefile_dir: str, project_data: Dict[str, Any],
                                incidents: List[Dict[str, Any]], output_path: str) -> str:
    """
    Generate overview map (async wrapper)

    Args:
        shapefile_dir: Directory containing shapefiles
        project_data: Project metadata
        incidents: List of incidents
        output_path: Output file path

    Returns:
        Path to generated map
    """
    generator = MapGenerator(shapefile_dir, project_data, incidents)
    return generator.generate_overview_map(output_path)
