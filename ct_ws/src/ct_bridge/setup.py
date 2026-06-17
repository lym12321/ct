from setuptools import find_packages, setup
import os
from glob import glob

package_name = "ct_bridge"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.launch.py")),
        (os.path.join("share", package_name, "config"), glob("config/*.yaml")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="fish",
    maintainer_email="fish@example.com",
    description="PX4 offboard control bridge — mocap transform, offboard hover, and pre-flight monitor",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "mocap_to_mavros = ct_bridge.mocap_to_mavros:main",
            "offboard_control = ct_bridge.offboard_control:main",
            "monitor = ct_bridge.monitor:main",
        ],
    },
)
