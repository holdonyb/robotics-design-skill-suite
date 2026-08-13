from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    use_sim_time = LaunchConfiguration("use_sim_time")
    model = PathJoinSubstitution([FindPackageShare("jx_mobile_manipulator_description"), "urdf", "reference_mobile_manipulator.urdf.xacro"])
    description = ParameterValue(Command(["xacro ", model, " use_sim:=1"]), value_type=str)
    return LaunchDescription([
        DeclareLaunchArgument("use_sim_time", default_value="true"),
        Node(package="robot_state_publisher", executable="robot_state_publisher", parameters=[{"robot_description": description, "use_sim_time": use_sim_time}]),
        Node(package="joint_state_publisher", executable="joint_state_publisher", parameters=[{"use_sim_time": use_sim_time}]),
        Node(package="rviz2", executable="rviz2", arguments=["-d", PathJoinSubstitution([FindPackageShare("jx_mobile_manipulator_description"), "rviz", "model.rviz"])], parameters=[{"use_sim_time": use_sim_time}]),
    ])
