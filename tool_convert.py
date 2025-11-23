# tool_convert.py
import base64

# 确保目录里有 icon.png
with open("icon.png", "rb") as image_file:
    encoded_string = base64.b64encode(image_file.read()).decode('utf-8')

# 将结果写入 icon_data.py
with open("icon_data.py", "w") as py_file:
    py_file.write(f'ICON_BASE64 = """{encoded_string}"""')

print("转换完成！已生成 icon_data.py 文件。")