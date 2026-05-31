from setuptools import find_packages, setup

package_name = "chess_arm_brain"

setup(
    name=package_name,
    version="0.0.1",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="neil",
    maintainer_email="neildesh@gmail.com",
    description=(
        "Chess game/logic library (authoritative python-chess board, vision "
        "changed-square move resolution, move->piece-action decomposition, "
        "lazy Stockfish) plus a thin ROS 2 node exposing the canonical brain "
        "services."
    ),
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "brain_node = chess_arm_brain.brain_node:main",
        ],
    },
)
