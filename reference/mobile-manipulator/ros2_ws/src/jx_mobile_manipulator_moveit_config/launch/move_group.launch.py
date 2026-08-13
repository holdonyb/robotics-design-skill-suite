from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
from moveit_configs_utils import MoveItConfigsBuilder
from pathlib import Path


def generate_launch_description():
    use_sim_time = LaunchConfiguration("use_sim_time")
    description_xacro = Path(get_package_share_directory("jx_mobile_manipulator_description")) / "urdf" / "reference_mobile_manipulator.urdf.xacro"
    config = (MoveItConfigsBuilder("reference_mobile_manipulator", package_name="jx_mobile_manipulator_moveit_config")
              .robot_description(file_path=description_xacro, mappings={"use_sim": "false"})
              .robot_description_semantic(file_path="config/reference_mobile_manipulator.srdf")
              .robot_description_kinematics(file_path="config/kinematics.yaml")
              .joint_limits(file_path="config/joint_limits.yaml")
              .planning_pipelines(pipelines=["ompl"], default_planning_pipeline="ompl")
              .trajectory_execution(file_path="config/moveit_controllers.yaml").to_moveit_configs())
    return LaunchDescription([DeclareLaunchArgument("use_sim_time", default_value="true"), Node(package="moveit_ros_move_group", executable="move_group", output="screen", parameters=[config.to_dict(), {"use_sim_time": use_sim_time}])])
