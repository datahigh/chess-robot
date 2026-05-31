from glob import glob
import os

from setuptools import find_packages, setup

package_name = 'chess_arm_orchestrator'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
            glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='neil',
    maintainer_email='neildesh@gmail.com',
    description=(
        'Game-loop state machine + pluggable executor + no-ROS dry-run for the '
        'chess-playing 6-DOF arm.'
    ),
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'orchestrator_node = chess_arm_orchestrator.orchestrator_node:main',
            'dry_run = chess_arm_orchestrator.dry_run:main',
            'play_sim_game = chess_arm_orchestrator.play_sim_game:main',
            'sim_game_driver = chess_arm_orchestrator.sim_game_driver:main',
        ],
    },
)
