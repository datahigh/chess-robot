from setuptools import find_packages, setup

package_name = "chess_arm_vision"

setup(
    name=package_name,
    version="0.0.1",
    packages=find_packages(exclude=["test"]),
    data_files=[
        (
            "share/ament_index/resource_index/packages",
            ["resource/" + package_name],
        ),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="neil",
    maintainer_email="neildesh@gmail.com",
    description=(
        "Phase-0 move-detection stub: per-square diff library + ROS 2 node "
        "that turns ground-truth simulator FENs into a DetectChanges service."
    ),
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "vision_node = chess_arm_vision.vision_node:main",
        ],
    },
)
