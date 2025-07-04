import subprocess
import sys
import os
import argparse

def extract_cover(video_path, output_path, map_param=None, detect_map=False, resize=False, min_size=(1280, 720), verbose=False):
    """
    提取视频封面（优先用户指定流，否则尝试附件流 -> 第一帧回退）
    """
    # 如果启用了 detect_map，则忽略 map_param 并探测 map
    if detect_map:
        detected_map = detect_cover_map(video_path, verbose)
        if detected_map:
            map_param = detected_map

    # 优先使用用户指定的流
    if map_param:
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-i", video_path,
            "-map", map_param,
            "-vframes", "1",
        ]
        if resize:
            cmd += ["-f", "image2pipe", "-vcodec", "png", "-"]  # 输出到stdout
            try:
                # 捕获FFmpeg输出到内存
                result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                
                # 使用PIL处理图像
                from PIL import Image
                import io
                
                img = Image.open(io.BytesIO(result.stdout))
                
                # 计算缩放尺寸
                width, height = img.size
                target_width = max(width, min_size[0])
                target_height = max(height, min_size[1])
                
                # 保持宽高比
                ratio = min(target_width/width, target_height/height)
                new_width = int(width * ratio)
                new_height = int(height * ratio)
                
                # 使用LANCZOS重采样
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                img.save(output_path, "JPEG", quality=95)
                return True
            except subprocess.CalledProcessError as e:
                if verbose:
                    print(f"封面提取失败（指定流模式）: {e.stderr.decode()}")
                return False
        else:
            cmd += ["-c", "copy"]
            cmd.append(output_path)
        try:
            subprocess.run(cmd, check=True, stderr=subprocess.PIPE)
            return True
        except subprocess.CalledProcessError as e:
            if verbose:
                print(f"封面提取失败（指定流模式）: {e.stderr.decode()}")
            return False

    # 未指定流时：仅尝试附件流，不再回退到第一帧
    try:
        # 尝试附件流中的图像（如封面）
        cmd_attach = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-i", video_path,
            "-map", "0:t",  # 所有附件流
            "-c", "copy",
            "-f", "image2",
            "-vframes", "1",
            output_path
        ]
        subprocess.run(cmd_attach, check=True, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError as e:
        if verbose:
            print(f"封面提取失败（附件流模式）: {e.stderr.decode()}")
        return False

def detect_cover_map(video_path, verbose=False):
    """
    探测视频封面所在的 map
    """
    try:
        # 获取附件流信息
        info_cmd = [
            "ffmpeg",
            "-hide_banner",
            "-i", video_path,
            # "-map", "0:t",  # 所有附件流
            "-c", "copy",
            "-f", "null",
            "-"
        ]
        # print("执行命令:", " ".join(info_cmd))  # 输出命令
        result = subprocess.run(info_cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, check=True)
        attachment_streams = result.stderr.decode().splitlines()
        # print(f"附件流信息：{attachment_streams}")

        # 遍历附件流，寻找可用的封面流
        for line in attachment_streams:
            if "Stream #0:" in line and "Video" in line and "(attached pic)" in line and "Subtitle" not in line: # "(attached pic)" 可能是ytb特有的
                stream_index = line.split("Stream #0:")[1].split(":")[0].split("[")[0]
                # 检查流的编码格式是否为 mjpeg
                if "mjpeg" in line.lower():
                    return f"0:{stream_index}"

    except subprocess.CalledProcessError as e:
        if verbose:
            print(f"封面流探测失败: {e.stderr.decode()}")
        else:
            print("警告：未找到可用的封面流")

def process_directory(input_dir, output_dir, map_param=None, detect_map=False, resize=False, min_size=(1280, 720), verbose=False):
    """处理目录中的所有 MP4 文件"""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    for root, _, files in os.walk(input_dir):
        for file in files:
            if file.lower().endswith(".mp4"):
                video_path = os.path.join(root, file)
                base_name = os.path.splitext(file)[0]
                output_path = os.path.join(output_dir, f"{base_name}.jpg")

                # 提取封面
                success = extract_cover(video_path, output_path, map_param, detect_map, resize, min_size, verbose)
                status = "成功" if success else "失败"
                print(f"[{status}] {file} -> {os.path.basename(output_path)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="批量提取 MP4 文件封面")
    parser.add_argument("--verbose", action="store_true", help="启用详细错误输出")
    parser.add_argument("-i", "--input", required=True, help="输入目录路径")
    parser.add_argument("-o", "--output", default=None, help="输出目录路径（默认：与输入目录相同）")
    parser.add_argument("-m", "--map", help="指定封面流通道（例如：0:3）")
    parser.add_argument("--detect_map", action="store_true", default=True, help="启用自动探测封面 map（默认关闭）")
    parser.add_argument("--resize", action="store_true", help="启用封面图自动缩放（默认关闭）")
    parser.add_argument("--min_size", default="1920x1080", 
                       help="最小输出尺寸（格式：宽x高，默认：1920x1080）")
    args = parser.parse_args()
    
    # Fix: Set default output directory to input directory when not provided
    if args.output is None:
        args.output = args.input

    # 解析min_size参数
    min_size = tuple(map(int, args.min_size.split('x')))
    if len(min_size) != 2:
        print(f"错误：无效的尺寸格式 - {args.min_size}")
        sys.exit(1)

    process_directory(args.input, args.output, args.map, args.detect_map, args.resize, min_size, args.verbose)