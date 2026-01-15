        # PHASE 1: Plot layers in exact z-order from experimental.md

        # STEP 2: Base Layers (Water and Boundaries)
        # 1. Water Polygons (Sea + River Polygons) - zorder=1
        print("   → Plotting water polygons (sea, river polygons)")
        sea_gdf.plot(ax=ax, color=COLORS['water_polygon'], edgecolor='none', zorder=1)
        rivers_poly_gdf.plot(ax=ax, color=COLORS['water_polygon'], edgecolor='none', zorder=1)

        # 2. LGA Boundaries - zorder=2
        print("   → Plotting LGA boundaries")
        boundaries_gdf.plot(ax=ax, facecolor='none', edgecolor=COLORS['boundaries'],
                           linewidth=0.5, zorder=2)

        # 3. River Lines - zorder=3
        print("   → Plotting river lines")
        rivers_gdf.plot(ax=ax, color=COLORS['river_lines'], linewidth=0.8, zorder=3)
        minor_rivers_gdf.plot(ax=ax, color=COLORS['river_lines'], linewidth=0.6, zorder=3)

        # STEP 3: Settlement Points and Labels - zorder=4
        print("   → Plotting all settlements with labels")
        for idx, row in settlements_gdf.iterrows():
            point = row.geometry
            if point.is_empty or not hasattr(point, 'x'):
                continue

            # Plot small black circle for settlement
            ax.plot(point.x, point.y, 'o', color=COLORS['settlement_marker'],
                   markersize=2.5, zorder=4)

            # Add settlement name label with white outline
            name = str(row.get('NAME', row.get('name', '')))
            if name:
                ax.text(point.x + 0.001, point.y, name, fontsize=7,
                       ha='left', va='center', color=COLORS['text_main'], zorder=4,
                       path_effects=[patheffects.withStroke(linewidth=2, foreground='white')])

        # STEP 4: Pipeline and Markers
        # 5. Pipeline Route - zorder=5
        print("   → Plotting pipeline route")
        pipeline_gdf.plot(ax=ax, color=COLORS['pipeline'], linewidth=3.5,
                         linestyle=(0, (6, 4)), zorder=5)  # (6,4) = dash-space pattern

        # 6. Pipeline Markers (Solid Circles) - zorder=6
        print("   → Adding pipeline markers")
        pipeline_coords = []
        for geom in pipeline_gdf.geometry:
            if hasattr(geom, 'coords'):
                pipeline_coords.extend(list(geom.coords))

        for coord in pipeline_coords[::3]:  # Every 3rd point
            circle = Circle((coord[0], coord[1]), radius=0.0025,
                           facecolor=COLORS['pipeline_markers'],
                           edgecolor='none',  # No outline - solid magenta
                           zorder=6)
            ax.add_patch(circle)

        # STEP 5: Pipeline Label - zorder=7
        # 7. Rotated Pipeline Label
        print("   → Adding pipeline label")
        if len(pipeline_coords) > 1:
            mid_idx = len(pipeline_coords) // 2
            p1 = pipeline_coords[mid_idx]
            p2 = pipeline_coords[mid_idx + 1] if mid_idx + 1 < len(pipeline_coords) else p1

            # Calculate rotation angle
            import numpy as np
            angle_rad = np.arctan2(p2[1] - p1[1], p2[0] - p1[0])
            angle_deg = np.degrees(angle_rad)

            pipeline_label = self.project.get('routeInspected', 'OBAMA-BRASS OANDO TRUNK LINE')
            ax.text(p1[0], p1[1], pipeline_label,
                   fontsize=10, weight='bold', rotation=angle_deg,
                   ha='center', va='bottom', color=COLORS['text_main'],
                   path_effects=[patheffects.withStroke(linewidth=3, foreground='white')],
                   zorder=7, rotation_mode='anchor')

        # STEP 6: Incidents and Callouts
        if incidents_gdf is not None and len(incidents_gdf) > 0:
            print(f"   → Plotting {len(incidents_gdf)} incidents with callouts")
            for idx, (incident, inc_data) in enumerate(zip(incidents_gdf.itertuples(), self.incidents)):
                x, y = incident.geometry.x, incident.geometry.y

                # Position callout (alternate left/right)
                callout_x = x + 0.08 if idx % 2 == 0 else x - 0.08
                callout_y = y + 0.02

                # 8. Connecting Line - zorder=8
                ax.plot([x, callout_x], [y, callout_y],
                       color=COLORS['incident_marker'],
                       linewidth=1.0, linestyle='--', zorder=8)

                # 9. Callout Box - zorder=9
                coords_text = f"(N{inc_data['latitude']:.6f}, E{inc_data['longitude']:.6f})"
                callout_text = f"Update: {inc_data['description']}\n{coords_text}"
                bbox_props = dict(boxstyle="round,pad=0.5",
                                 facecolor=COLORS['callout_bg'],
                                 edgecolor=COLORS['callout_border'],
                                 linewidth=1)

                ax.text(callout_x, callout_y, callout_text, fontsize=7,
                       ha='center', va='center', bbox=bbox_props, zorder=9,
                       linespacing=1.4)

                # 10. Incident Marker - zorder=10
                circle = Circle((x, y), radius=0.005,
                               facecolor=COLORS['incident_marker'],
                               edgecolor=COLORS['incident_outline'],
                               linewidth=2, zorder=10)
                ax.add_patch(circle)
