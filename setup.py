from setuptools import setup, find_packages

setup(
    name="parking-audit",
    version="1.0.0",
    description="智慧停车数据核对命令行工具",
    author="Parking Audit Team",
    packages=find_packages(),
    install_requires=[
        "pandas>=1.5.0",
        "openpyxl>=3.0.0",
    ],
    entry_points={
        "console_scripts": [
            "parking-audit=parking_audit.main:main",
        ],
    },
    python_requires=">=3.8",
)
