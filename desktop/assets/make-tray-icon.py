#!/usr/bin/env python3
"""Rasterise tray-icon.svg into the PNGs a status item / tray needs.

Run on macOS (uses AppKit to rasterise; NSImage has read SVG since Ventura):

    python3 desktop/assets/make-tray-icon.py

Writes tray-icon.png (16pt) and tray-icon@2x.png (32px). Electron and rumps
both pick the @2x variant automatically from the 1x filename, so BOTH must
exist and stay in step -- shipping only one leaves the icon blurry on a Retina
display or missing on a non-Retina one.

Committed rather than generated at build time: the desktop app is packaged by
electron-builder on machines that may not be macOS, and a tray with no image is
an invisible click target.
"""

import sys
from pathlib import Path

ASSETS = Path(__file__).resolve().parent
SOURCE = ASSETS / "tray-icon.svg"
SIZES = {"tray-icon.png": 16, "tray-icon@2x.png": 32}


def main() -> int:
    try:
        from AppKit import (NSBitmapImageRep, NSCalibratedRGBColorSpace, NSGraphicsContext,
                            NSImage, NSPNGFileType)
        from Foundation import NSData, NSMakeRect
    except ImportError:
        print("This script needs PyObjC (pip install pyobjc-framework-Cocoa) on macOS.",
              file=sys.stderr)
        return 1

    svg = SOURCE.read_bytes()
    image = NSImage.alloc().initWithData_(NSData.dataWithBytes_length_(svg, len(svg)))
    if image is None:
        print(f"could not read {SOURCE}", file=sys.stderr)
        return 1

    for name, px in SIZES.items():
        rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
            None, px, px, 8, 4, True, False, NSCalibratedRGBColorSpace, 0, 0)
        rep.setSize_((px, px))
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.setCurrentContext_(
            NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep))
        # Drawn onto a cleared context: the background must stay transparent or
        # the template silhouette becomes a filled square, which is the exact
        # bug this asset exists to fix.
        image.drawInRect_fromRect_operation_fraction_(
            NSMakeRect(0, 0, px, px), NSMakeRect(0, 0, 0, 0), 1, 1.0)
        NSGraphicsContext.restoreGraphicsState()

        target = ASSETS / name
        data = rep.representationUsingType_properties_(NSPNGFileType, {})
        data.writeToFile_atomically_(str(target), True)
        print(f"wrote {target.name} ({px}x{px})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
