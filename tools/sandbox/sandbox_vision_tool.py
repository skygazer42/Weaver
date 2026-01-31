"""
Sandbox Vision Tool for E2B Sandbox Image Analysis Operations.

This module provides image analysis capabilities in an E2B sandbox:
- OCR (Optical Character Recognition) for text extraction
- Image metadata extraction
- Image resizing and conversion
- Basic image analysis (colors, dimensions)
- QR/Barcode reading

Similar to Manus's sb_vision_tool.py but adapted for Weaver's E2B integration.

Usage:
    from tools.sandbox.sandbox_vision_tool import build_sandbox_vision_tools

    tools = build_sandbox_vision_tools(thread_id="thread_123")
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from typing import Any, Dict, List, Optional

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def _get_sandbox_session(thread_id: str):
    """Get sandbox session for a thread."""
    from tools.sandbox.sandbox_browser_session import sandbox_browser_sessions

    return sandbox_browser_sessions.get(thread_id)


def _get_event_emitter(thread_id: str):
    """Get event emitter for a thread."""
    from agent.core.events import get_emitter_sync

    return get_emitter_sync(thread_id)


class _SandboxVisionBaseTool(BaseTool):
    """Base class for sandbox vision tools."""

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
                logger.warning(f"[sandbox_vision] Failed to emit event: {e}")

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

    def _ensure_dependencies(self, sandbox, packages: List[str]) -> bool:
        """Ensure required packages are installed in sandbox."""
        try:
            for pkg in packages:
                result = sandbox.commands.run(f"pip show {pkg}", timeout=30)
                if result.exit_code != 0:
                    logger.info(f"[sandbox_vision] Installing {pkg}...")
                    install_result = sandbox.commands.run(f"pip install {pkg}", timeout=120)
                    if install_result.exit_code != 0:
                        return False
            return True
        except Exception as e:
            logger.warning(f"[sandbox_vision] Failed to install dependencies: {e}")
            return False


class ExtractTextInput(BaseModel):
    """Input for extract_text (OCR)."""

    image_path: str = Field(description="Path to the image file in sandbox")
    language: str = Field(
        default="eng", description="OCR language code (e.g., 'eng', 'chi_sim', 'jpn')"
    )


class SandboxExtractTextTool(_SandboxVisionBaseTool):
    """Extract text from an image using OCR."""

    name: str = "sandbox_extract_text"
    description: str = (
        "Extract text from an image using OCR (Optical Character Recognition). "
        "Supports multiple languages. Returns the extracted text."
    )
    args_schema: type[BaseModel] = ExtractTextInput

    def _run(
        self,
        image_path: str,
        language: str = "eng",
    ) -> Dict[str, Any]:
        start_time = self._emit_tool_start("extract_text", {"image_path": image_path})

        try:
            sandbox = self._get_sandbox()
            if not sandbox:
                raise RuntimeError("Sandbox not initialized. Start sandbox browser first.")

            # Install pytesseract and tesseract-ocr
            install_cmd = "apt-get update && apt-get install -y tesseract-ocr && pip install pytesseract pillow"
            sandbox.commands.run(install_cmd, timeout=180)

            # Install language pack if not English
            if language != "eng":
                sandbox.commands.run(f"apt-get install -y tesseract-ocr-{language}", timeout=60)

            full_path = f"{self.workspace_path}/{image_path.lstrip('/')}"

            python_code = f'''
import pytesseract
from PIL import Image
import json

try:
    image = Image.open("{full_path}")
    text = pytesseract.image_to_string(image, lang="{language}")

    # Also get bounding boxes for words
    data = pytesseract.image_to_data(image, lang="{language}", output_type=pytesseract.Output.DICT)

    # Count words with confidence > 0
    words = [w for w, c in zip(data['text'], data['conf']) if w.strip() and int(c) > 0]

    result = {{
        "text": text.strip(),
        "word_count": len(words),
        "language": "{language}",
    }}
    print(json.dumps(result))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
'''
            result = sandbox.commands.run(f"python3 -c '{python_code}'", timeout=60)

            try:
                output = json.loads(result.stdout.strip())
                if "error" in output:
                    raise RuntimeError(output["error"])
            except json.JSONDecodeError:
                raise RuntimeError(f"OCR failed: {result.stderr}")

            result = {"success": True, "path": image_path, **output}

            self._emit_tool_result("extract_text", result, start_time, True)
            return result

        except Exception as e:
            self._emit_tool_result("extract_text", {"error": str(e)}, start_time, False)
            return {"success": False, "error": str(e)}


class GetImageInfoInput(BaseModel):
    """Input for get_image_info."""

    image_path: str = Field(description="Path to the image file in sandbox")


class SandboxGetImageInfoTool(_SandboxVisionBaseTool):
    """Get information about an image."""

    name: str = "sandbox_get_image_info"
    description: str = (
        "Get detailed information about an image including dimensions, "
        "format, mode, and basic color analysis."
    )
    args_schema: type[BaseModel] = GetImageInfoInput

    def _run(self, image_path: str) -> Dict[str, Any]:
        start_time = self._emit_tool_start("get_image_info", {"image_path": image_path})

        try:
            sandbox = self._get_sandbox()
            if not sandbox:
                raise RuntimeError("Sandbox not initialized.")

            # Ensure Pillow is installed
            if not self._ensure_dependencies(sandbox, ["Pillow"]):
                return {"success": False, "error": "Failed to install Pillow"}

            full_path = f"{self.workspace_path}/{image_path.lstrip('/')}"

            python_code = f'''
from PIL import Image
from collections import Counter
import json
import os

try:
    image = Image.open("{full_path}")

    # Get file size
    file_size = os.path.getsize("{full_path}")

    # Get dominant colors (sample pixels)
    if image.mode in ('RGB', 'RGBA'):
        # Resize for faster processing
        small = image.copy()
        small.thumbnail((100, 100))
        pixels = list(small.getdata())

        # Count colors
        if image.mode == 'RGBA':
            pixels = [(r, g, b) for r, g, b, a in pixels]

        color_counts = Counter(pixels)
        top_colors = [
            {{"rgb": list(c), "count": n}}
            for c, n in color_counts.most_common(5)
        ]
    else:
        top_colors = []

    # Check if image has transparency
    has_transparency = image.mode in ('RGBA', 'LA') or (
        image.mode == 'P' and 'transparency' in image.info
    )

    result = {{
        "width": image.width,
        "height": image.height,
        "format": image.format,
        "mode": image.mode,
        "file_size_bytes": file_size,
        "has_transparency": has_transparency,
        "top_colors": top_colors,
        "dpi": image.info.get('dpi'),
    }}
    print(json.dumps(result))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
'''
            result = sandbox.commands.run(f"python3 -c '{python_code}'", timeout=30)

            try:
                output = json.loads(result.stdout.strip())
                if "error" in output:
                    raise RuntimeError(output["error"])
            except json.JSONDecodeError:
                raise RuntimeError(f"Failed to get image info: {result.stderr}")

            result = {"success": True, "path": image_path, **output}

            self._emit_tool_result("get_image_info", result, start_time, True)
            return result

        except Exception as e:
            self._emit_tool_result("get_image_info", {"error": str(e)}, start_time, False)
            return {"success": False, "error": str(e)}


class ResizeImageInput(BaseModel):
    """Input for resize_image."""

    image_path: str = Field(description="Path to the source image")
    output_path: str = Field(description="Path for the resized image")
    width: Optional[int] = Field(
        default=None, description="Target width (maintains aspect ratio if height not set)"
    )
    height: Optional[int] = Field(
        default=None, description="Target height (maintains aspect ratio if width not set)"
    )
    quality: int = Field(default=85, description="JPEG quality (1-100)")


class SandboxResizeImageTool(_SandboxVisionBaseTool):
    """Resize an image."""

    name: str = "sandbox_resize_image"
    description: str = (
        "Resize an image to specified dimensions. "
        "If only width or height is provided, aspect ratio is maintained."
    )
    args_schema: type[BaseModel] = ResizeImageInput

    def _run(
        self,
        image_path: str,
        output_path: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        quality: int = 85,
    ) -> Dict[str, Any]:
        start_time = self._emit_tool_start(
            "resize_image",
            {
                "image_path": image_path,
                "width": width,
                "height": height,
            },
        )

        try:
            sandbox = self._get_sandbox()
            if not sandbox:
                raise RuntimeError("Sandbox not initialized.")

            if not width and not height:
                return {"success": False, "error": "At least width or height must be specified"}

            if not self._ensure_dependencies(sandbox, ["Pillow"]):
                return {"success": False, "error": "Failed to install Pillow"}

            full_input = f"{self.workspace_path}/{image_path.lstrip('/')}"
            full_output = f"{self.workspace_path}/{output_path.lstrip('/')}"

            # Create output directory
            parent_dir = "/".join(full_output.split("/")[:-1])
            if parent_dir:
                sandbox.commands.run(f"mkdir -p {parent_dir}")

            width_arg = width if width else "None"
            height_arg = height if height else "None"

            python_code = f'''
from PIL import Image
import json

try:
    image = Image.open("{full_input}")
    orig_width, orig_height = image.size

    target_width = {width_arg}
    target_height = {height_arg}

    if target_width and not target_height:
        # Calculate height maintaining aspect ratio
        ratio = target_width / orig_width
        target_height = int(orig_height * ratio)
    elif target_height and not target_width:
        # Calculate width maintaining aspect ratio
        ratio = target_height / orig_height
        target_width = int(orig_width * ratio)

    # Resize
    resized = image.resize((target_width, target_height), Image.Resampling.LANCZOS)

    # Save
    output_path = "{full_output}"
    if output_path.lower().endswith('.jpg') or output_path.lower().endswith('.jpeg'):
        if resized.mode == 'RGBA':
            resized = resized.convert('RGB')
        resized.save(output_path, 'JPEG', quality={quality})
    else:
        resized.save(output_path)

    result = {{
        "original_size": [orig_width, orig_height],
        "new_size": [target_width, target_height],
    }}
    print(json.dumps(result))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
'''
            result = sandbox.commands.run(f"python3 -c '{python_code}'", timeout=30)

            try:
                output = json.loads(result.stdout.strip())
                if "error" in output:
                    raise RuntimeError(output["error"])
            except json.JSONDecodeError:
                raise RuntimeError(f"Failed to resize image: {result.stderr}")

            result = {
                "success": True,
                "input_path": image_path,
                "output_path": output_path,
                **output,
            }

            self._emit_tool_result("resize_image", result, start_time, True)
            return result

        except Exception as e:
            self._emit_tool_result("resize_image", {"error": str(e)}, start_time, False)
            return {"success": False, "error": str(e)}


class ConvertImageInput(BaseModel):
    """Input for convert_image."""

    image_path: str = Field(description="Path to the source image")
    output_path: str = Field(
        description="Path for the converted image (format determined by extension)"
    )
    quality: int = Field(default=85, description="JPEG quality (1-100)")


class SandboxConvertImageTool(_SandboxVisionBaseTool):
    """Convert an image to a different format."""

    name: str = "sandbox_convert_image"
    description: str = (
        "Convert an image to a different format (e.g., PNG to JPEG, WEBP to PNG). "
        "Output format is determined by the file extension."
    )
    args_schema: type[BaseModel] = ConvertImageInput

    def _run(
        self,
        image_path: str,
        output_path: str,
        quality: int = 85,
    ) -> Dict[str, Any]:
        start_time = self._emit_tool_start(
            "convert_image",
            {
                "image_path": image_path,
                "output_path": output_path,
            },
        )

        try:
            sandbox = self._get_sandbox()
            if not sandbox:
                raise RuntimeError("Sandbox not initialized.")

            if not self._ensure_dependencies(sandbox, ["Pillow"]):
                return {"success": False, "error": "Failed to install Pillow"}

            full_input = f"{self.workspace_path}/{image_path.lstrip('/')}"
            full_output = f"{self.workspace_path}/{output_path.lstrip('/')}"

            # Create output directory
            parent_dir = "/".join(full_output.split("/")[:-1])
            if parent_dir:
                sandbox.commands.run(f"mkdir -p {parent_dir}")

            python_code = f'''
from PIL import Image
import json
import os

try:
    image = Image.open("{full_input}")
    output_path = "{full_output}"

    # Determine format from extension
    ext = os.path.splitext(output_path)[1].lower()
    format_map = {{
        '.jpg': 'JPEG',
        '.jpeg': 'JPEG',
        '.png': 'PNG',
        '.gif': 'GIF',
        '.bmp': 'BMP',
        '.webp': 'WEBP',
        '.tiff': 'TIFF',
        '.tif': 'TIFF',
    }}
    output_format = format_map.get(ext, 'PNG')

    # Handle RGBA for JPEG
    if output_format == 'JPEG' and image.mode == 'RGBA':
        image = image.convert('RGB')

    # Save with appropriate options
    save_kwargs = {{}}
    if output_format == 'JPEG':
        save_kwargs['quality'] = {quality}
    elif output_format == 'PNG':
        save_kwargs['optimize'] = True

    image.save(output_path, output_format, **save_kwargs)

    result = {{
        "input_format": image.format or "unknown",
        "output_format": output_format,
        "size": os.path.getsize(output_path),
    }}
    print(json.dumps(result))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
'''
            result = sandbox.commands.run(f"python3 -c '{python_code}'", timeout=30)

            try:
                output = json.loads(result.stdout.strip())
                if "error" in output:
                    raise RuntimeError(output["error"])
            except json.JSONDecodeError:
                raise RuntimeError(f"Failed to convert image: {result.stderr}")

            result = {
                "success": True,
                "input_path": image_path,
                "output_path": output_path,
                **output,
            }

            self._emit_tool_result("convert_image", result, start_time, True)
            return result

        except Exception as e:
            self._emit_tool_result("convert_image", {"error": str(e)}, start_time, False)
            return {"success": False, "error": str(e)}


class CropImageInput(BaseModel):
    """Input for crop_image."""

    image_path: str = Field(description="Path to the source image")
    output_path: str = Field(description="Path for the cropped image")
    left: int = Field(description="Left coordinate of crop box")
    top: int = Field(description="Top coordinate of crop box")
    right: int = Field(description="Right coordinate of crop box")
    bottom: int = Field(description="Bottom coordinate of crop box")


class SandboxCropImageTool(_SandboxVisionBaseTool):
    """Crop an image to specified coordinates."""

    name: str = "sandbox_crop_image"
    description: str = (
        "Crop an image to specified coordinates (left, top, right, bottom). "
        "Coordinates are in pixels from the top-left corner."
    )
    args_schema: type[BaseModel] = CropImageInput

    def _run(
        self,
        image_path: str,
        output_path: str,
        left: int,
        top: int,
        right: int,
        bottom: int,
    ) -> Dict[str, Any]:
        start_time = self._emit_tool_start(
            "crop_image",
            {
                "image_path": image_path,
                "box": [left, top, right, bottom],
            },
        )

        try:
            sandbox = self._get_sandbox()
            if not sandbox:
                raise RuntimeError("Sandbox not initialized.")

            if not self._ensure_dependencies(sandbox, ["Pillow"]):
                return {"success": False, "error": "Failed to install Pillow"}

            full_input = f"{self.workspace_path}/{image_path.lstrip('/')}"
            full_output = f"{self.workspace_path}/{output_path.lstrip('/')}"

            # Create output directory
            parent_dir = "/".join(full_output.split("/")[:-1])
            if parent_dir:
                sandbox.commands.run(f"mkdir -p {parent_dir}")

            python_code = f'''
from PIL import Image
import json

try:
    image = Image.open("{full_input}")

    # Validate crop box
    left, top, right, bottom = {left}, {top}, {right}, {bottom}
    if left >= right or top >= bottom:
        raise ValueError("Invalid crop box: left must be < right and top must be < bottom")
    if left < 0 or top < 0 or right > image.width or bottom > image.height:
        raise ValueError(f"Crop box out of bounds. Image size: {{image.width}}x{{image.height}}")

    cropped = image.crop((left, top, right, bottom))
    cropped.save("{full_output}")

    result = {{
        "original_size": [image.width, image.height],
        "crop_box": [left, top, right, bottom],
        "new_size": [cropped.width, cropped.height],
    }}
    print(json.dumps(result))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
'''
            result = sandbox.commands.run(f"python3 -c '{python_code}'", timeout=30)

            try:
                output = json.loads(result.stdout.strip())
                if "error" in output:
                    raise RuntimeError(output["error"])
            except json.JSONDecodeError:
                raise RuntimeError(f"Failed to crop image: {result.stderr}")

            result = {
                "success": True,
                "input_path": image_path,
                "output_path": output_path,
                **output,
            }

            self._emit_tool_result("crop_image", result, start_time, True)
            return result

        except Exception as e:
            self._emit_tool_result("crop_image", {"error": str(e)}, start_time, False)
            return {"success": False, "error": str(e)}


class ReadQRCodeInput(BaseModel):
    """Input for read_qr_code."""

    image_path: str = Field(description="Path to the image containing QR code")


class SandboxReadQRCodeTool(_SandboxVisionBaseTool):
    """Read QR code or barcode from an image."""

    name: str = "sandbox_read_qr_code"
    description: str = (
        "Read and decode QR codes or barcodes from an image. "
        "Returns the decoded data and code type."
    )
    args_schema: type[BaseModel] = ReadQRCodeInput

    def _run(self, image_path: str) -> Dict[str, Any]:
        start_time = self._emit_tool_start("read_qr_code", {"image_path": image_path})

        try:
            sandbox = self._get_sandbox()
            if not sandbox:
                raise RuntimeError("Sandbox not initialized.")

            # Install pyzbar
            sandbox.commands.run("apt-get update && apt-get install -y libzbar0", timeout=60)
            if not self._ensure_dependencies(sandbox, ["pyzbar", "Pillow"]):
                return {"success": False, "error": "Failed to install pyzbar"}

            full_path = f"{self.workspace_path}/{image_path.lstrip('/')}"

            python_code = f'''
from PIL import Image
from pyzbar import pyzbar
import json

try:
    image = Image.open("{full_path}")
    codes = pyzbar.decode(image)

    results = []
    for code in codes:
        results.append({{
            "data": code.data.decode('utf-8', errors='replace'),
            "type": code.type,
            "rect": {{
                "left": code.rect.left,
                "top": code.rect.top,
                "width": code.rect.width,
                "height": code.rect.height,
            }}
        }})

    result = {{
        "codes": results,
        "count": len(results),
    }}
    print(json.dumps(result))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
'''
            result = sandbox.commands.run(f"python3 -c '{python_code}'", timeout=30)

            try:
                output = json.loads(result.stdout.strip())
                if "error" in output:
                    raise RuntimeError(output["error"])
            except json.JSONDecodeError:
                raise RuntimeError(f"Failed to read QR code: {result.stderr}")

            result = {"success": True, "path": image_path, **output}

            self._emit_tool_result("read_qr_code", result, start_time, True)
            return result

        except Exception as e:
            self._emit_tool_result("read_qr_code", {"error": str(e)}, start_time, False)
            return {"success": False, "error": str(e)}


class CompareImagesInput(BaseModel):
    """Input for compare_images."""

    image1_path: str = Field(description="Path to the first image")
    image2_path: str = Field(description="Path to the second image")


class SandboxCompareImagesTool(_SandboxVisionBaseTool):
    """Compare two images for similarity."""

    name: str = "sandbox_compare_images"
    description: str = (
        "Compare two images and calculate their similarity. "
        "Returns a similarity score and difference metrics."
    )
    args_schema: type[BaseModel] = CompareImagesInput

    def _run(
        self,
        image1_path: str,
        image2_path: str,
    ) -> Dict[str, Any]:
        start_time = self._emit_tool_start(
            "compare_images",
            {
                "image1_path": image1_path,
                "image2_path": image2_path,
            },
        )

        try:
            sandbox = self._get_sandbox()
            if not sandbox:
                raise RuntimeError("Sandbox not initialized.")

            if not self._ensure_dependencies(sandbox, ["Pillow", "numpy"]):
                return {"success": False, "error": "Failed to install dependencies"}

            full_path1 = f"{self.workspace_path}/{image1_path.lstrip('/')}"
            full_path2 = f"{self.workspace_path}/{image2_path.lstrip('/')}"

            python_code = f'''
from PIL import Image
import numpy as np
import json

try:
    img1 = Image.open("{full_path1}")
    img2 = Image.open("{full_path2}")

    # Check dimensions
    same_size = img1.size == img2.size

    # Resize for comparison if different sizes
    if not same_size:
        size = (min(img1.width, img2.width), min(img1.height, img2.height))
        img1 = img1.resize(size, Image.Resampling.LANCZOS)
        img2 = img2.resize(size, Image.Resampling.LANCZOS)

    # Convert to RGB
    if img1.mode != 'RGB':
        img1 = img1.convert('RGB')
    if img2.mode != 'RGB':
        img2 = img2.convert('RGB')

    # Convert to numpy arrays
    arr1 = np.array(img1, dtype=np.float32)
    arr2 = np.array(img2, dtype=np.float32)

    # Calculate Mean Squared Error
    mse = np.mean((arr1 - arr2) ** 2)

    # Calculate Structural Similarity (simplified)
    # Normalize to 0-1
    arr1_norm = arr1 / 255.0
    arr2_norm = arr2 / 255.0

    # Compute means
    mean1 = np.mean(arr1_norm)
    mean2 = np.mean(arr2_norm)

    # Compute correlation coefficient as simple similarity
    flat1 = arr1_norm.flatten()
    flat2 = arr2_norm.flatten()
    correlation = np.corrcoef(flat1, flat2)[0, 1]

    # Similarity score (0-100)
    similarity = max(0, correlation * 100)

    result = {{
        "same_size": same_size,
        "image1_size": list(img1.size),
        "image2_size": list(img2.size),
        "mse": float(mse),
        "similarity_percent": round(float(similarity), 2),
        "identical": mse == 0,
    }}
    print(json.dumps(result))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
'''
            result = sandbox.commands.run(f"python3 -c '{python_code}'", timeout=30)

            try:
                output = json.loads(result.stdout.strip())
                if "error" in output:
                    raise RuntimeError(output["error"])
            except json.JSONDecodeError:
                raise RuntimeError(f"Failed to compare images: {result.stderr}")

            result = {
                "success": True,
                "image1_path": image1_path,
                "image2_path": image2_path,
                **output,
            }

            self._emit_tool_result("compare_images", result, start_time, True)
            return result

        except Exception as e:
            self._emit_tool_result("compare_images", {"error": str(e)}, start_time, False)
            return {"success": False, "error": str(e)}


def build_sandbox_vision_tools(
    thread_id: str,
    emit_events: bool = True,
) -> List[BaseTool]:
    """
    Build sandbox vision tools for a thread.

    Args:
        thread_id: Thread/conversation ID
        emit_events: Whether to emit events

    Returns:
        List of vision tools
    """
    return [
        SandboxExtractTextTool(thread_id=thread_id, emit_events=emit_events),
        SandboxGetImageInfoTool(thread_id=thread_id, emit_events=emit_events),
        SandboxResizeImageTool(thread_id=thread_id, emit_events=emit_events),
        SandboxConvertImageTool(thread_id=thread_id, emit_events=emit_events),
        SandboxCropImageTool(thread_id=thread_id, emit_events=emit_events),
        SandboxReadQRCodeTool(thread_id=thread_id, emit_events=emit_events),
        SandboxCompareImagesTool(thread_id=thread_id, emit_events=emit_events),
    ]
