"""
Photo Annotator Service

Adds annotations to drone aerial photos with pipeline and incident labels.
"""

from PIL import Image, ImageDraw, ImageFont
from typing import Dict, Any, List
from pathlib import Path
import os


class PhotoAnnotator:
    """Photo annotation with dynamic text and arrows"""

    def __init__(self, pipeline_name: str):
        """
        Initialize annotator

        Args:
            pipeline_name: Name of the pipeline (e.g., "Obama-Brass OANDO Trunk Line")
        """
        self.pipeline_name = pipeline_name

        # Try to load Arial font, fallback to default
        try:
            self.font_path = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
            if not os.path.exists(self.font_path):
                self.font_path = None
        except:
            self.font_path = None

    def annotate_photo(self, input_path: str, output_path: str,
                      incident_description: str, latitude: float, longitude: float,
                      distance_meters: float = None) -> str:
        """
        Annotate a single photo

        Args:
            input_path: Path to original photo
            output_path: Path to save annotated photo
            incident_description: Description of the incident
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            distance_meters: Optional distance indicator

        Returns:
            Path to annotated photo
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Photo not found: {input_path}")

        print(f"   📸 Annotating: {os.path.basename(input_path)}")

        # Load image
        img = Image.open(input_path)
        width, height = img.size
        draw = ImageDraw.Draw(img)

        # Dynamic font sizing (4% of image height)
        font_size = int(height * 0.04)

        # Load font
        try:
            if self.font_path and os.path.exists(self.font_path):
                font = ImageFont.truetype(self.font_path, font_size)
                font_small = ImageFont.truetype(self.font_path, int(font_size * 0.85))
            else:
                font = ImageFont.load_default()
                font_small = ImageFont.load_default()
        except:
            font = ImageFont.load_default()
            font_small = ImageFont.load_default()

        # === 1. Pipeline RoW Label (top 1/3) ===
        pipeline_text = f"{self.pipeline_name} RoW"
        pipeline_x = width // 2
        pipeline_y = height // 3

        # Draw text with outline (black stroke + white fill)
        self._draw_outlined_text(draw, pipeline_text, pipeline_x, pipeline_y,
                                font, 'white', 'black', 3)

        # Arrow pointing down-left from pipeline label
        arrow_start = (pipeline_x - width // 10, pipeline_y + int(font_size * 1.5))
        arrow_end = (pipeline_x - width // 5, pipeline_y + int(font_size * 4))
        self._draw_arrow(draw, arrow_start, arrow_end, 'red', 4)

        # === 2. Incident Description (bottom-right quadrant) ===
        incident_x = (width * 3) // 4
        incident_y = (height * 3) // 4

        # Split long descriptions
        wrapped_desc = self._wrap_text(incident_description, 40)
        y_offset = 0

        for line in wrapped_desc:
            self._draw_outlined_text(draw, line, incident_x, incident_y + y_offset,
                                    font_small, 'white', 'black', 3)
            y_offset += int(font_size * 1.2)

        # Coordinates below description
        coord_text = f"(N{latitude:.6f}, E{longitude:.6f})"
        self._draw_outlined_text(draw, coord_text, incident_x, incident_y + y_offset,
                                font_small, 'white', 'black', 3)

        # Arrow pointing down-right from incident label
        arrow_start2 = (incident_x + width // 20, incident_y + y_offset + int(font_size * 1.5))
        arrow_end2 = (incident_x + width // 10, incident_y + y_offset + int(font_size * 3.5))
        self._draw_arrow(draw, arrow_start2, arrow_end2, 'red', 4)

        # === 3. Optional: Distance indicator (top-left) ===
        if distance_meters is not None:
            # Semi-transparent black background
            box_coords = [(20, 20), (220, 70)]
            draw.rectangle(box_coords, fill=(0, 0, 0, 128), outline='black', width=2)

            # Distance text
            distance_text = f"{distance_meters:.1f}m"
            draw.text((120, 45), distance_text, font=font, fill='white', anchor='mm')

        # Save annotated image
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        img.save(output_path, quality=95)

        print(f"      ✅ Saved: {os.path.basename(output_path)}")

        return output_path

    def _draw_outlined_text(self, draw, text: str, x: int, y: int,
                           font, fill_color: str, outline_color: str, outline_width: int):
        """Draw text with outline effect"""
        # Draw outline
        for adj_x in range(-outline_width, outline_width + 1):
            for adj_y in range(-outline_width, outline_width + 1):
                draw.text((x + adj_x, y + adj_y), text, font=font,
                         fill=outline_color, anchor='mm')

        # Draw main text
        draw.text((x, y), text, font=font, fill=fill_color, anchor='mm')

    def _draw_arrow(self, draw, start: tuple, end: tuple, color: str, width: int):
        """Draw arrow from start to end point"""
        import math

        # Draw line
        draw.line([start, end], fill=color, width=width)

        # Calculate arrowhead angle
        angle = math.atan2(end[1] - start[1], end[0] - start[0])
        arrow_length = 20

        # Arrowhead points
        left_point = (
            end[0] - arrow_length * math.cos(angle - math.pi / 6),
            end[1] - arrow_length * math.sin(angle - math.pi / 6)
        )
        right_point = (
            end[0] - arrow_length * math.cos(angle + math.pi / 6),
            end[1] - arrow_length * math.sin(angle + math.pi / 6)
        )

        # Draw arrowhead
        draw.polygon([end, left_point, right_point], fill=color)

    def _wrap_text(self, text: str, max_length: int = 40) -> List[str]:
        """Wrap text into multiple lines"""
        words = text.split()
        lines = []
        current_line = ''

        for word in words:
            test_line = f"{current_line} {word}".strip()
            if len(test_line) <= max_length:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word

        if current_line:
            lines.append(current_line)

        return lines if lines else [text]


async def annotate_incident_photos(pipeline_name: str, incidents: List[Dict[str, Any]],
                                   upload_dir: str) -> List[Dict[str, Any]]:
    """
    Annotate all photos for all incidents

    Args:
        pipeline_name: Name of the pipeline
        incidents: List of incidents with photos
        upload_dir: Base upload directory

    Returns:
        Updated incidents list with annotatedPhotos paths
    """
    print("📸 Annotating incident photos...")

    annotator = PhotoAnnotator(pipeline_name)
    updated_incidents = []

    for incident in incidents:
        original_photos = incident.get('originalPhotos', [])
        annotated_photos = []

        if original_photos:
            for photo_path in original_photos:
                if os.path.exists(photo_path):
                    # Generate output path
                    filename = os.path.basename(photo_path)
                    output_dir = os.path.join(upload_dir, 'annotated')
                    output_path = os.path.join(output_dir, f"annotated_{filename}")

                    try:
                        # Annotate photo
                        result_path = annotator.annotate_photo(
                            input_path=photo_path,
                            output_path=output_path,
                            incident_description=incident['description'],
                            latitude=incident['latitude'],
                            longitude=incident['longitude']
                        )
                        annotated_photos.append(result_path)

                    except Exception as e:
                        print(f"      ⚠️  Failed to annotate {filename}: {e}")
                        # Use original photo as fallback
                        annotated_photos.append(photo_path)

        # Update incident with annotated photos
        incident_copy = incident.copy()
        incident_copy['annotatedPhotos'] = annotated_photos
        updated_incidents.append(incident_copy)

    print(f"   ✅ Annotated {sum(len(inc.get('annotatedPhotos', [])) for inc in updated_incidents)} photos")

    return updated_incidents
