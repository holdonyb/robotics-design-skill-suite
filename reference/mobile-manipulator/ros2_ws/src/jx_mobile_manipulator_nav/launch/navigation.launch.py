from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    params = PathJoinSubstitution([FindPackageShare("jx_mobile_manipulator_nav"), "config", "nav2_params.yaml"])
    map_file = PathJoinSubstitution([FindPackageShare("jx_mobile_manipulator_nav"), "maps", "empty.yaml"])
    bringup = IncludeLaunchDescription(PythonLaunchDescriptionSource(PathJoinSubstitution([FindPackageShare("nav2_bringup"), "launch", "bringup_launch.py"])), launch_arguments={"use_sim_time": "True", "params_file": params, "map": map_file, "use_localization": "True", "autostart": "True", "use_composition": "False"}.items())
    return LaunchDescription([bringup])
