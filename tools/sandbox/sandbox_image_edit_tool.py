"""
Sandbox Image Edit Tool for advanced image editing operations.

This module provides advanced image editing in an E2B sandbox:
- Filters (blur, sharpen, emboss, contour, edge detection)
- Adjustments (brightness, contrast, saturation, hue)
- Transformations (rotate, flip, mirror)
- Overlays (watermark, text overlay)
- Effects (grayscale, sepia, invert, posterize)
- Composition (merge, overlay images)

Similar to Manus's sb_image_edit_tool.py but adapted for Weaver.

Usage:
    from tools.sandbox.sandbox_image_edit_tool import build_image_edit_tools

    tools = build_image_edit_tools(thread_id="thread_123")
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Literal, Optional

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# Filter types
FilterType = Literal[
    "blur", "gaussian_blur", "sharpen", "edge_enhance", "emboss", "contour", "detail", "smooth"
]

# Effect types
EffectType = Literal[
    "grayscale", "sepia", "invert", "posterize", "solarize", "auto_contrast", "equalize"
]


def _get_sandbox_session(thread_id: str):
    """Get sandbox session for a thread."""
    from tools.sandbox.sandbox_browser_session import sandbox_browser_sessions

    return sandbox_browser_sessions.get(thread_id)


def _get_event_emitter(thread_id: str):
    """Get event emitter for a thread."""
    from agent.core.events import get_emitter_sync

    return get_emitter_sync(thread_id)


class _ImageEditBaseTool(BaseTool):
    """Base class for image edit tools."""

    thread_id: str = "default"
    emit_events: bool = True
    workspace_path: str = "/workspace"

    def _get_sandbox(self):
        """Get the E2B sandbox instance."""
        session = _get_sandbox_session(self.thread_id)
        if session and hasattr(session, "_handles") and session._handles:
            return session._handles.sandbox
        return None

    def _emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Emit an event."""
        if not self.emit_events:
            return
        emitter = _get_event_emitter(self.thread_id)
        if emitter:
            try:
                emitter.emit_sync(event_type, data)
            except Exception as e:
                logger.warning(f"[image_edit] Failed to emit event: {e}")

    def _emit_tool_start(self, action: str, args: Dict[str, Any]) -> float:
        """Emit tool start event."""
        start_time = time.time()
        self._emit_event(
            "tool_start",
            {
                "tool": self.name,
                "action": action,
                "args": args,
                "thread_id": self.thread_id,
            },
        )
        return start_time

    def _emit_tool_result(
        self,
        action: str,
        result: Dict[str, Any],
        start_time: float,
        success: bool = True,
    ) -> None:
        """Emit tool result event."""
        duration_ms = (time.time() - start_time) * 1000
        self._emit_event(
            "tool_result",
            {
                "tool": self.name,
                "action": action,
                "success": success,
                "duration_ms": round(duration_ms, 2),
            },
        )

    def _ensure_pillow(self, sandbox) -> bool:
        """Ensure Pillow is installed in sandbox."""
        try:
            result = sandbox.commands.run("pip show Pillow", timeout=30)
            if result.exit_code != 0:
                install_result = sandbox.commands.run("pip install Pillow numpy", timeout=120)
                return install_result.exit_code == 0
            return True
        except Exception as e:
            logger.warning(f"[image_edit] Failed to install Pillow: {e}")
            return False


class ApplyFilterInput(BaseModel):
    """Input for apply_filter."""

    image_path: str = Field(description="Path to the source image")
    output_path: str = Field(description="Path for the output image")
    filter_type: FilterType = Field(description="Filter to apply")
    intensity: float = Field(
        default=1.0, ge=0.1, le=3.0, description="Filter intensity (0.1-3.0, default 1.0)"
    )


class ApplyFilterTool(_ImageEditBaseTool):
    """Apply a filter to an image."""

    name: str = "apply_image_filter"
    description: str = (
        "Apply a filter to an image. "
        "Filters: blur, gaussian_blur, sharpen, edge_enhance, emboss, contour, detail, smooth."
    )
    args_schema: type[BaseModel] = ApplyFilterInput

    def _run(
        self,
        image_path: str,
        output_path: str,
        filter_type: FilterType,
        intensity: float = 1.0,
    ) -> Dict[str, Any]:
        start_time = self._emit_tool_start(
            "apply_filter",
            {
                "image_path": image_path,
                "filter_type": filter_type,
            },
        )

        try:
            sandbox = self._get_sandbox()
            if not sandbox:
                raise RuntimeError("Sandbox not initialized.")

            if not self._ensure_pillow(sandbox):
                return {"success": False, "error": "Failed to install Pillow"}

            full_input = f"{self.workspace_path}/{image_path.lstrip('/')}"
            full_output = f"{self.workspace_path}/{output_path.lstrip('/')}"

            # Create output directory
            parent_dir = "/".join(full_output.split("/")[:-1])
            if parent_dir:
                sandbox.commands.run(f"mkdir -p {parent_dir}")

            python_code = f'''
from PIL import Image, ImageFilter
import json

try:
    image = Image.open("{full_input}")

    filter_map = {{
        "blur": ImageFilter.BLUR,
        "gaussian_blur": ImageFilter.GaussianBlur(radius={int(intensity * 2)}),
        "sharpen": ImageFilter.SHARPEN,
        "edge_enhance": ImageFilter.EDGE_ENHANCE,
        "emboss": ImageFilter.EMBOSS,
        "contour": ImageFilter.CONTOUR,
        "detail": ImageFilter.DETAIL,
        "smooth": ImageFilter.SMOOTH,
    }}

    filter_obj = filter_map.get("{filter_type}")

    # Apply filter multiple times for intensity > 1
    result = image
    for _ in range(int({intensity})):
        result = result.filter(filter_obj)

    result.save("{full_output}")

    print(json.dumps({{
        "width": result.width,
        "height": result.height,
        "mode": result.mode
    }}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
'''
            result = sandbox.commands.run(f"python3 -c '{python_code}'", timeout=30)

            try:
                output = json.loads(result.stdout.strip())
                if "error" in output:
                    raise RuntimeError(output["error"])
            except json.JSONDecodeError:
                raise RuntimeError(f"Failed to apply filter: {result.stderr}")

            result = {
                "success": True,
                "message": f"Applied '{filter_type}' filter",
                "input_path": image_path,
                "output_path": output_path,
                "filter": filter_type,
                **output,
            }

            self._emit_tool_result("apply_filter", result, start_time, True)
            return result

        except Exception as e:
            self._emit_tool_result("apply_filter", {"error": str(e)}, start_time, False)
            return {"success": False, "error": str(e)}


class ApplyEffectInput(BaseModel):
    """Input for apply_effect."""

    image_path: str = Field(description="Path to the source image")
    output_path: str = Field(description="Path for the output image")
    effect_type: EffectType = Field(description="Effect to apply")


class ApplyEffectTool(_ImageEditBaseTool):
    """Apply an effect to an image."""

    name: str = "apply_image_effect"
    description: str = (
        "Apply a color effect to an image. "
        "Effects: grayscale, sepia, invert, posterize, solarize, auto_contrast, equalize."
    )
    args_schema: type[BaseModel] = ApplyEffectInput

    def _run(
        self,
        image_path: str,
        output_path: str,
        effect_type: EffectType,
    ) -> Dict[str, Any]:
        start_time = self._emit_tool_start(
            "apply_effect",
            {
                "image_path": image_path,
                "effect_type": effect_type,
            },
        )

        try:
            sandbox = self._get_sandbox()
            if not sandbox:
                raise RuntimeError("Sandbox not initialized.")

            if not self._ensure_pillow(sandbox):
                return {"success": False, "error": "Failed to install Pillow"}

            full_input = f"{self.workspace_path}/{image_path.lstrip('/')}"
            full_output = f"{self.workspace_path}/{output_path.lstrip('/')}"

            parent_dir = "/".join(full_output.split("/")[:-1])
            if parent_dir:
                sandbox.commands.run(f"mkdir -p {parent_dir}")

            python_code = f'''
from PIL import Image, ImageOps, ImageEnhance
import json

try:
    image = Image.open("{full_input}")

    # Convert to RGB if necessary
    if image.mode in ('RGBA', 'LA'):
        background = Image.new('RGB', image.size, (255, 255, 255))
        if image.mode == 'RGBA':
            background.paste(image, mask=image.split()[3])
        else:
            background.paste(image, mask=image.split()[1])
        image = background
    elif image.mode != 'RGB':
        image = image.convert('RGB')

    effect = "{effect_type}"

    if effect == "grayscale":
        result = ImageOps.grayscale(image)
    elif effect == "sepia":
        # Convert to grayscale first
        gray = ImageOps.grayscale(image)
        # Apply sepia tone
        sepia = Image.merge('RGB', (
            gray.point(lambda x: min(255, x + 40)),  # R
            gray.point(lambda x: x),                  # G
            gray.point(lambda x: max(0, x - 30))      # B
        ))
        result = sepia
    elif effect == "invert":
        result = ImageOps.invert(image)
    elif effect == "posterize":
        result = ImageOps.posterize(image, 4)
    elif effect == "solarize":
        result = ImageOps.solarize(image, threshold=128)
    elif effect == "auto_contrast":
        result = ImageOps.autocontrast(image)
    elif effect == "equalize":
        result = ImageOps.equalize(image)
    else:
        result = image

    result.save("{full_output}")

    print(json.dumps({{
        "width": result.width,
        "height": result.height,
        "mode": result.mode
    }}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
'''
            result = sandbox.commands.run(f"python3 -c '{python_code}'", timeout=30)

            try:
                output = json.loads(result.stdout.strip())
                if "error" in output:
                    raise RuntimeError(output["error"])
            except json.JSONDecodeError:
                raise RuntimeError(f"Failed to apply effect: {result.stderr}")

            result = {
                "success": True,
                "message": f"Applied '{effect_type}' effect",
                "input_path": image_path,
                "output_path": output_path,
                "effect": effect_type,
                **output,
            }

            self._emit_tool_result("apply_effect", result, start_time, True)
            return result

        except Exception as e:
            self._emit_tool_result("apply_effect", {"error": str(e)}, start_time, False)
            return {"success": False, "error": str(e)}


class AdjustImageInput(BaseModel):
    """Input for adjust_image."""

    image_path: str = Field(description="Path to the source image")
    output_path: str = Field(description="Path for the output image")
    brightness: float = Field(
        default=1.0, ge=0.0, le=3.0, description="Brightness (1.0 = original)"
    )
    contrast: float = Field(default=1.0, ge=0.0, le=3.0, description="Contrast (1.0 = original)")
    saturation: float = Field(
        default=1.0, ge=0.0, le=3.0, description="Saturation (1.0 = original)"
    )
    sharpness: float = Field(default=1.0, ge=0.0, le=3.0, description="Sharpness (1.0 = original)")


class AdjustImageTool(_ImageEditBaseTool):
    """Adjust image properties."""

    name: str = "adjust_image"
    description: str = (
        "Adjust brightness, contrast, saturation, and sharpness of an image. "
        "Values: 1.0 = original, <1.0 = decrease, >1.0 = increase."
    )
    args_schema: type[BaseModel] = AdjustImageInput

    def _run(
        self,
        image_path: str,
        output_path: str,
        brightness: float = 1.0,
        contrast: float = 1.0,
        saturation: float = 1.0,
        sharpness: float = 1.0,
    ) -> Dict[str, Any]:
        start_time = self._emit_tool_start(
            "adjust_image",
            {
                "image_path": image_path,
            },
        )

        try:
            sandbox = self._get_sandbox()
            if not sandbox:
                raise RuntimeError("Sandbox not initialized.")

            if not self._ensure_pillow(sandbox):
                return {"success": False, "error": "Failed to install Pillow"}

            full_input = f"{self.workspace_path}/{image_path.lstrip('/')}"
            full_output = f"{self.workspace_path}/{output_path.lstrip('/')}"

            parent_dir = "/".join(full_output.split("/")[:-1])
            if parent_dir:
                sandbox.commands.run(f"mkdir -p {parent_dir}")

            python_code = f'''
from PIL import Image, ImageEnhance
import json

try:
    image = Image.open("{full_input}")

    # Apply adjustments
    if {brightness} != 1.0:
        enhancer = ImageEnhance.Brightness(image)
        image = enhancer.enhance({brightness})

    if {contrast} != 1.0:
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance({contrast})

    if {saturation} != 1.0:
        enhancer = ImageEnhance.Color(image)
        image = enhancer.enhance({saturation})

    if {sharpness} != 1.0:
        enhancer = ImageEnhance.Sharpness(image)
        image = enhancer.enhance({sharpness})

    image.save("{full_output}")

    print(json.dumps({{
        "width": image.width,
        "height": image.height,
        "adjustments": {{
            "brightness": {brightness},
            "contrast": {contrast},
            "saturation": {saturation},
            "sharpness": {sharpness}
        }}
    }}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
'''
            result = sandbox.commands.run(f"python3 -c '{python_code}'", timeout=30)

            try:
                output = json.loads(result.stdout.strip())
                if "error" in output:
                    raise RuntimeError(output["error"])
            except json.JSONDecodeError:
                raise RuntimeError(f"Failed to adjust image: {result.stderr}")

            result = {
                "success": True,
                "message": "Image adjusted",
                "input_path": image_path,
                "output_path": output_path,
                **output,
            }

            self._emit_tool_result("adjust_image", result, start_time, True)
            return result

        except Exception as e:
            self._emit_tool_result("adjust_image", {"error": str(e)}, start_time, False)
            return {"success": False, "error": str(e)}


class RotateFlipInput(BaseModel):
    """Input for rotate_flip."""

    image_path: str = Field(description="Path to the source image")
    output_path: str = Field(description="Path for the output image")
    rotate_degrees: int = Field(
        default=0, description="Rotation angle in degrees (0, 90, 180, 270)"
    )
    flip_horizontal: bool = Field(default=False, description="Flip horizontally")
    flip_vertical: bool = Field(default=False, description="Flip vertically")


class RotateFlipTool(_ImageEditBaseTool):
    """Rotate or flip an image."""

    name: str = "rotate_flip_image"
    description: str = "Rotate and/or flip an image. Rotation supports 0, 90, 180, 270 degrees."
    args_schema: type[BaseModel] = RotateFlipInput

    def _run(
        self,
        image_path: str,
        output_path: str,
        rotate_degrees: int = 0,
        flip_horizontal: bool = False,
        flip_vertical: bool = False,
    ) -> Dict[str, Any]:
        start_time = self._emit_tool_start(
            "rotate_flip",
            {
                "image_path": image_path,
                "rotate": rotate_degrees,
            },
        )

        try:
            sandbox = self._get_sandbox()
            if not sandbox:
                raise RuntimeError("Sandbox not initialized.")

            if not self._ensure_pillow(sandbox):
                return {"success": False, "error": "Failed to install Pillow"}

            full_input = f"{self.workspace_path}/{image_path.lstrip('/')}"
            full_output = f"{self.workspace_path}/{output_path.lstrip('/')}"

            parent_dir = "/".join(full_output.split("/")[:-1])
            if parent_dir:
                sandbox.commands.run(f"mkdir -p {parent_dir}")

            python_code = f'''
from PIL import Image
import json

try:
    image = Image.open("{full_input}")

    # Rotate
    if {rotate_degrees} != 0:
        # PIL rotates counter-clockwise, we want clockwise
        image = image.rotate(-{rotate_degrees}, expand=True)

    # Flip
    if {flip_horizontal}:
        image = image.transpose(Image.FLIP_LEFT_RIGHT)
    if {flip_vertical}:
        image = image.transpose(Image.FLIP_TOP_BOTTOM)

    image.save("{full_output}")

    print(json.dumps({{
        "width": image.width,
        "height": image.height,
        "transforms": {{
            "rotate": {rotate_degrees},
            "flip_horizontal": {flip_horizontal},
            "flip_vertical": {flip_vertical}
        }}
    }}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
'''
            result = sandbox.commands.run(f"python3 -c '{python_code}'", timeout=30)

            try:
                output = json.loads(result.stdout.strip())
                if "error" in output:
                    raise RuntimeError(output["error"])
            except json.JSONDecodeError:
                raise RuntimeError(f"Failed to transform image: {result.stderr}")

            result = {
                "success": True,
                "message": "Image transformed",
                "input_path": image_path,
                "output_path": output_path,
                **output,
            }

            self._emit_tool_result("rotate_flip", result, start_time, True)
            return result

        except Exception as e:
            self._emit_tool_result("rotate_flip", {"error": str(e)}, start_time, False)
            return {"success": False, "error": str(e)}


class AddWatermarkInput(BaseModel):
    """Input for add_watermark."""

    image_path: str = Field(description="Path to the source image")
    output_path: str = Field(description="Path for the output image")
    text: str = Field(description="Watermark text")
    position: Literal["center", "bottom-right", "bottom-left", "top-right", "top-left"] = Field(
        default="bottom-right", description="Watermark position"
    )
    opacity: float = Field(default=0.5, ge=0.1, le=1.0, description="Watermark opacity (0.1-1.0)")
    font_size: int = Field(default=36, description="Font size")
    color: str = Field(default="FFFFFF", description="Text color (hex)")


class AddWatermarkTool(_ImageEditBaseTool):
    """Add a text watermark to an image."""

    name: str = "add_watermark"
    description: str = (
        "Add a text watermark to an image. "
        "Position options: center, bottom-right, bottom-left, top-right, top-left."
    )
    args_schema: type[BaseModel] = AddWatermarkInput

    def _run(
        self,
        image_path: str,
        output_path: str,
        text: str,
        position: str = "bottom-right",
        opacity: float = 0.5,
        font_size: int = 36,
        color: str = "FFFFFF",
    ) -> Dict[str, Any]:
        start_time = self._emit_tool_start(
            "add_watermark",
            {
                "image_path": image_path,
                "position": position,
            },
        )

        try:
            sandbox = self._get_sandbox()
            if not sandbox:
                raise RuntimeError("Sandbox not initialized.")

            if not self._ensure_pillow(sandbox):
                return {"success": False, "error": "Failed to install Pillow"}

            full_input = f"{self.workspace_path}/{image_path.lstrip('/')}"
            full_output = f"{self.workspace_path}/{output_path.lstrip('/')}"

            parent_dir = "/".join(full_output.split("/")[:-1])
            if parent_dir:
                sandbox.commands.run(f"mkdir -p {parent_dir}")

            text_escaped = text.replace('"', '\\"').replace("'", "\\'")

            python_code = f'''
from PIL import Image, ImageDraw, ImageFont
import json

try:
    image = Image.open("{full_input}")

    # Convert to RGBA for transparency
    if image.mode != 'RGBA':
        image = image.convert('RGBA')

    # Create watermark layer
    watermark = Image.new('RGBA', image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(watermark)

    # Try to use a font, fall back to default
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", {font_size})
    except:
        font = ImageFont.load_default()

    # Get text size
    text = "{text_escaped}"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # Calculate position
    padding = 20
    position = "{position}"

    if position == "center":
        x = (image.width - text_width) // 2
        y = (image.height - text_height) // 2
    elif position == "bottom-right":
        x = image.width - text_width - padding
        y = image.height - text_height - padding
    elif position == "bottom-left":
        x = padding
        y = image.height - text_height - padding
    elif position == "top-right":
        x = image.width - text_width - padding
        y = padding
    elif position == "top-left":
        x = padding
        y = padding
    else:
        x = image.width - text_width - padding
        y = image.height - text_height - padding

    # Parse color
    color_hex = "{color}"
    r = int(color_hex[0:2], 16)
    g = int(color_hex[2:4], 16)
    b = int(color_hex[4:6], 16)
    alpha = int({opacity} * 255)

    # Draw text with shadow for visibility
    draw.text((x+2, y+2), text, font=font, fill=(0, 0, 0, alpha // 2))  # Shadow
    draw.text((x, y), text, font=font, fill=(r, g, b, alpha))

    # Composite
    result = Image.alpha_composite(image, watermark)

    # Convert back to RGB if saving as JPEG
    if "{full_output}".lower().endswith(('.jpg', '.jpeg')):
        result = result.convert('RGB')

    result.save("{full_output}")

    print(json.dumps({{
        "width": result.width,
        "height": result.height,
        "watermark_position": "{position}"
    }}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
'''
            result = sandbox.commands.run(f"python3 -c '{python_code}'", timeout=30)

            try:
                output = json.loads(result.stdout.strip())
                if "error" in output:
                    raise RuntimeError(output["error"])
            except json.JSONDecodeError:
                raise RuntimeError(f"Failed to add watermark: {result.stderr}")

            result = {
                "success": True,
                "message": f"Watermark added at {position}",
                "input_path": image_path,
                "output_path": output_path,
                **output,
            }

            self._emit_tool_result("add_watermark", result, start_time, True)
            return result

        except Exception as e:
            self._emit_tool_result("add_watermark", {"error": str(e)}, start_time, False)
            return {"success": False, "error": str(e)}


class OverlayImagesInput(BaseModel):
    """Input for overlay_images."""

    base_image_path: str = Field(description="Path to the base image")
    overlay_image_path: str = Field(description="Path to the overlay image")
    output_path: str = Field(description="Path for the output image")
    x: int = Field(default=0, description="X position of overlay")
    y: int = Field(default=0, description="Y position of overlay")
    opacity: float = Field(default=1.0, ge=0.0, le=1.0, description="Overlay opacity")
    resize_overlay: Optional[List[int]] = Field(
        default=None, description="Resize overlay to [width, height]"
    )


class OverlayImagesTool(_ImageEditBaseTool):
    """Overlay one image on another."""

    name: str = "overlay_images"
    description: str = (
        "Overlay one image on top of another. "
        "Specify position and opacity. Optionally resize the overlay."
    )
    args_schema: type[BaseModel] = OverlayImagesInput

    def _run(
        self,
        base_image_path: str,
        overlay_image_path: str,
        output_path: str,
        x: int = 0,
        y: int = 0,
        opacity: float = 1.0,
        resize_overlay: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        start_time = self._emit_tool_start(
            "overlay_images",
            {
                "base_image_path": base_image_path,
                "overlay_image_path": overlay_image_path,
            },
        )

        try:
            sandbox = self._get_sandbox()
            if not sandbox:
                raise RuntimeError("Sandbox not initialized.")

            if not self._ensure_pillow(sandbox):
                return {"success": False, "error": "Failed to install Pillow"}

            full_base = f"{self.workspace_path}/{base_image_path.lstrip('/')}"
            full_overlay = f"{self.workspace_path}/{overlay_image_path.lstrip('/')}"
            full_output = f"{self.workspace_path}/{output_path.lstrip('/')}"

            parent_dir = "/".join(full_output.split("/")[:-1])
            if parent_dir:
                sandbox.commands.run(f"mkdir -p {parent_dir}")

            resize_str = str(resize_overlay) if resize_overlay else "None"

            python_code = f'''
from PIL import Image
import json

try:
    base = Image.open("{full_base}")
    overlay = Image.open("{full_overlay}")

    # Convert to RGBA
    if base.mode != 'RGBA':
        base = base.convert('RGBA')
    if overlay.mode != 'RGBA':
        overlay = overlay.convert('RGBA')

    # Resize overlay if specified
    resize = {resize_str}
    if resize:
        overlay = overlay.resize(tuple(resize), Image.Resampling.LANCZOS)

    # Adjust opacity
    if {opacity} < 1.0:
        alpha = overlay.split()[3]
        alpha = alpha.point(lambda x: int(x * {opacity}))
        overlay.putalpha(alpha)

    # Paste overlay
    base.paste(overlay, ({x}, {y}), overlay)

    # Convert back if saving as JPEG
    if "{full_output}".lower().endswith(('.jpg', '.jpeg')):
        base = base.convert('RGB')

    base.save("{full_output}")

    print(json.dumps({{
        "width": base.width,
        "height": base.height
    }}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
'''
            result = sandbox.commands.run(f"python3 -c '{python_code}'", timeout=30)

            try:
                output = json.loads(result.stdout.strip())
                if "error" in output:
                    raise RuntimeError(output["error"])
            except json.JSONDecodeError:
                raise RuntimeError(f"Failed to overlay images: {result.stderr}")

            result = {
                "success": True,
                "message": "Images overlaid",
                "base_image": base_image_path,
                "overlay_image": overlay_image_path,
                "output_path": output_path,
                **output,
            }

            self._emit_tool_result("overlay_images", result, start_time, True)
            return result

        except Exception as e:
            self._emit_tool_result("overlay_images", {"error": str(e)}, start_time, False)
            return {"success": False, "error": str(e)}


class CreateThumbnailInput(BaseModel):
    """Input for create_thumbnail."""

    image_path: str = Field(description="Path to the source image")
    output_path: str = Field(description="Path for the thumbnail")
    max_size: int = Field(default=128, description="Maximum width or height")
    maintain_aspect: bool = Field(default=True, description="Maintain aspect ratio")


class CreateThumbnailTool(_ImageEditBaseTool):
    """Create a thumbnail from an image."""

    name: str = "create_thumbnail"
    description: str = (
        "Create a thumbnail from an image. Specify max size; aspect ratio is maintained by default."
    )
    args_schema: type[BaseModel] = CreateThumbnailInput

    def _run(
        self,
        image_path: str,
        output_path: str,
        max_size: int = 128,
        maintain_aspect: bool = True,
    ) -> Dict[str, Any]:
        start_time = self._emit_tool_start(
            "create_thumbnail",
            {
                "image_path": image_path,
                "max_size": max_size,
            },
        )

        try:
            sandbox = self._get_sandbox()
            if not sandbox:
                raise RuntimeError("Sandbox not initialized.")

            if not self._ensure_pillow(sandbox):
                return {"success": False, "error": "Failed to install Pillow"}

            full_input = f"{self.workspace_path}/{image_path.lstrip('/')}"
            full_output = f"{self.workspace_path}/{output_path.lstrip('/')}"

            parent_dir = "/".join(full_output.split("/")[:-1])
            if parent_dir:
                sandbox.commands.run(f"mkdir -p {parent_dir}")

            python_code = f'''
from PIL import Image
import json

try:
    image = Image.open("{full_input}")
    original_size = image.size

    if {maintain_aspect}:
        image.thumbnail(({max_size}, {max_size}), Image.Resampling.LANCZOS)
    else:
        image = image.resize(({max_size}, {max_size}), Image.Resampling.LANCZOS)

    image.save("{full_output}")

    print(json.dumps({{
        "original_size": list(original_size),
        "thumbnail_size": [image.width, image.height]
    }}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
'''
            result = sandbox.commands.run(f"python3 -c '{python_code}'", timeout=30)

            try:
                output = json.loads(result.stdout.strip())
                if "error" in output:
                    raise RuntimeError(output["error"])
            except json.JSONDecodeError:
                raise RuntimeError(f"Failed to create thumbnail: {result.stderr}")

            result = {
                "success": True,
                "message": "Thumbnail created",
                "input_path": image_path,
                "output_path": output_path,
                **output,
            }

            self._emit_tool_result("create_thumbnail", result, start_time, True)
            return result

        except Exception as e:
            self._emit_tool_result("create_thumbnail", {"error": str(e)}, start_time, False)
            return {"success": False, "error": str(e)}


def build_image_edit_tools(
    thread_id: str,
    emit_events: bool = True,
) -> List[BaseTool]:
    """
    Build image edit tools for a thread.

    Args:
        thread_id: Thread/conversation ID
        emit_events: Whether to emit events

    Returns:
        List of image edit tools
    """
    return [
        ApplyFilterTool(thread_id=thread_id, emit_events=emit_events),
        ApplyEffectTool(thread_id=thread_id, emit_events=emit_events),
        AdjustImageTool(thread_id=thread_id, emit_events=emit_events),
        RotateFlipTool(thread_id=thread_id, emit_events=emit_events),
        AddWatermarkTool(thread_id=thread_id, emit_events=emit_events),
        OverlayImagesTool(thread_id=thread_id, emit_events=emit_events),
        CreateThumbnailTool(thread_id=thread_id, emit_events=emit_events),
    ]
