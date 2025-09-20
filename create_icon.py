from PIL import Image, ImageDraw
import struct

def create_video_downloader_icon():
    # Create icon sizes needed for Windows
    sizes = [16, 32, 48, 256]

    # Create a list to hold all icon images
    images = []

    for size in sizes:
        # Create a new image with transparent background
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Draw background circle
        bg_color = (59, 130, 246, 255)  # Blue color matching the SVG
        draw.ellipse([2, 2, size-2, size-2], fill=bg_color)

        # Draw play button triangle (scaled for each size)
        if size >= 32:
            # Only draw detailed elements for larger sizes
            triangle_size = size // 4
            x_center = size // 2
            y_center = size // 2

            # Play triangle
            triangle_points = [
                (x_center - triangle_size, y_center - triangle_size//2),
                (x_center - triangle_size, y_center + triangle_size//2),
                (x_center + triangle_size//2, y_center)
            ]
            draw.polygon(triangle_points, fill=(255, 255, 255, 255))

            # Draw download arrow for larger sizes
            if size >= 48:
                arrow_x = x_center + triangle_size
                arrow_y = y_center
                draw.rectangle([arrow_x-2, arrow_y-6, arrow_x+2, arrow_y+4], fill=(16, 185, 129, 255))
                draw.polygon([arrow_x-4, arrow_y+4, arrow_x, arrow_y+8, arrow_x+4, arrow_y+4], fill=(16, 185, 129, 255))

        images.append(img)

    # Save as ICO file
    images[0].save('video_downloader.ico', format='ICO', sizes=[(img.size[0], img.size[1]) for img in images], append_images=images[1:])

    print(f"Created icon with sizes: {[img.size for img in images]}")

if __name__ == "__main__":
    try:
        create_video_downloader_icon()
        print("Icon created successfully!")
    except ImportError:
        print("PIL (Pillow) is required. Install with: pip install Pillow")
    except Exception as e:
        print(f"Error creating icon: {e}")
