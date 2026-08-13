from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    use_sim_time = LaunchConfiguration("use_sim_time")
    params = PathJoinSubstitution([FindPackageShare("jx_mobile_manipulator_nav"), "config", "nav2_params.yaml"])
    map_file = PathJoinSubstitution([FindPackageShare("jx_mobile_manipulator_nav"), "maps", "empty.yaml"])
    bringup = IncludeLaunchDescription(PythonLaunchDescriptionSource(PathJoinSubstitution([FindPackageShare("nav2_bringup"), "launch", "bringup_launch.py"])), launch_arguments={"use_sim_time": use_sim_time, "params_file": params, "map": map_file, "use_localization": "true", "autostart": "true", "use_composition": "False"}.items())
    return LaunchDescription([DeclareLaunchArgument("use_sim_time", default_value="true"), bringup])
