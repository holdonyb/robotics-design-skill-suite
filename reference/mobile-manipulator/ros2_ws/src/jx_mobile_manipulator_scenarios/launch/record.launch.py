from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    use_sim_time = LaunchConfiguration("use_sim_time")
    output = LaunchConfiguration("output")
    record = ExecuteProcess(cmd=["ros2", "bag", "record", "--storage", "mcap", "--output", output, "/clock", "/joint_states", "/odom", "/imu/data"], output="screen")
    return LaunchDescription([DeclareLaunchArgument("use_sim_time", default_value="true"), DeclareLaunchArgument("output", default_value="reference_trace"), record])
