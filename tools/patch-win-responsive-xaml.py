"""让 Windows 版支持小窗口（1/4 屏 = 720×450）：给布局元素命名 + 加可折叠侧栏。

只做 XAML 侧的结构准备（命名 + UniformGrid），适配逻辑在 MainWindow 的 ApplyResponsive 里。
"""

import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, 'dsh-manager-win', 'MainWindow.xaml')

PAIRS = [
    # 1) 侧栏列与容器、内容滚动区
    ('<ColumnDefinition Width="248" />',
     '<ColumnDefinition x:Name="SidebarCol" Width="248" />'),
    ('                    <Grid Margin="16,26,16,18">',
     '                    <Grid x:Name="SidebarInner" Margin="16,26,16,18">'),
    ('                    <ScrollViewer Grid.Row="1" VerticalScrollBarVisibility="Auto" Padding="30,25,30,15">',
     '                    <ScrollViewer x:Name="ContentScroll" Grid.Row="1" VerticalScrollBarVisibility="Auto" Padding="30,25,30,15">'),
    # 2) 品牌文字
    ('                                <TextBlock Text="DeepSeek Harness" FontSize="13" FontWeight="SemiBold"\n'
     '                                           Foreground="{DynamicResource Text}" />\n'
     '                                <TextBlock FontSize="11" Margin="0,4,0,0" Foreground="{DynamicResource Muted}">',
     '                                <TextBlock x:Name="BrandTitle" Text="DeepSeek Harness" FontSize="13" FontWeight="SemiBold"\n'
     '                                           Foreground="{DynamicResource Text}" />\n'
     '                                <TextBlock x:Name="BrandSub" FontSize="11" Margin="0,4,0,0" Foreground="{DynamicResource Muted}">'),
    ('                            <StackPanel Grid.Column="1" Margin="11,0,0,0" VerticalAlignment="Center">',
     '                            <StackPanel x:Name="BrandCopy" Grid.Column="1" Margin="11,0,0,0" VerticalAlignment="Center">'),
    # 3) 「我的实例」标题行 + 新建实例按钮
    ('                        <Grid Grid.Row="1" Height="32" Margin="8,0,8,7">',
     '                        <Grid x:Name="InstancesHeader" Grid.Row="1" Height="32" Margin="8,0,8,7">'),
    ('                            <StackPanel Orientation="Horizontal" VerticalAlignment="Center">\n'
     '                                <TextBlock Text="我的实例" FontSize="11" FontWeight="SemiBold"',
     '                            <StackPanel x:Name="InstancesHeaderCopy" Orientation="Horizontal" VerticalAlignment="Center">\n'
     '                                <TextBlock Text="我的实例" FontSize="11" FontWeight="SemiBold"'),
    ('                            <StackPanel Orientation="Horizontal">\n'
     '                                <Path Width="15" Height="15" Data="{StaticResource Icon.plus}"\n'
     '                                      Style="{StaticResource IconPath}" />\n'
     '                                <TextBlock Text="新建实例" FontSize="11" Margin="7,0,0,0"\n'
     '                                           Foreground="{DynamicResource Muted}" />',
     '                            <StackPanel x:Name="NewInstanceCopy" Orientation="Horizontal">\n'
     '                                <Path Width="15" Height="15" Data="{StaticResource Icon.plus}"\n'
     '                                      Style="{StaticResource IconPath}" />\n'
     '                                <TextBlock x:Name="NewInstanceLabel" Text="新建实例" FontSize="11" Margin="7,0,0,0"\n'
     '                                           Foreground="{DynamicResource Muted}" />'),
    # 4) 底部导航文字（加名字以便折叠）
    ('                            <TextBlock Text="工作空间" FontSize="10" FontWeight="SemiBold"\n'
     '                                       Foreground="{DynamicResource Subtle}" Margin="11,0,0,8" />',
     '                            <TextBlock x:Name="WorkspaceCaption" Text="工作空间" FontSize="10" FontWeight="SemiBold"\n'
     '                                       Foreground="{DynamicResource Subtle}" Margin="11,0,0,8" />'),
    # 5) 页头描述 + 页脚
    ('                                    <TextBlock Text="管理服务、窗口与扩展，让实例始终保持最佳状态。" FontSize="11"\n'
     '                                               Margin="0,7,0,0" Foreground="{DynamicResource Muted}" />',
     '                                    <TextBlock x:Name="PageDesc" Text="管理服务、窗口与扩展，让实例始终保持最佳状态。" FontSize="11"\n'
     '                                               Margin="0,7,0,0" Foreground="{DynamicResource Muted}" />'),
    ('                            <Grid Margin="2,12,2,0" Height="20">',
     '                            <Grid x:Name="PageFooter" Margin="2,12,2,0" Height="20">'),
    # 6) 概览区：给容器和两张卡命名（窄屏时要改成上下堆叠）
    ('                            <!-- 概览两卡 -->\n'
     '                            <Grid Margin="0,0,0,0">',
     '                            <!-- 概览两卡 -->\n'
     '                            <Grid x:Name="OverviewGrid" Margin="0,0,0,0">'),
    ('                                <Border Grid.Column="0" Style="{StaticResource CardStyle}" Padding="20,18">',
     '                                <Border x:Name="InstanceCard" Grid.Column="0" Style="{StaticResource CardStyle}" Padding="20,18">'),
    ('                                <Border Grid.Column="2" Style="{StaticResource CardStyle}" Padding="20,18">',
     '                                <Border x:Name="ControlCard" Grid.Column="2" Style="{StaticResource CardStyle}" Padding="20,18">'),
]

# 常用功能：Grid(4 列) -> UniformGrid（列数可运行时改）
QUICK_REPLACE = [
    ('''                            <Grid x:Name="QuickGrid">
                                <Grid.ColumnDefinitions>
                                    <ColumnDefinition />
                                    <ColumnDefinition />
                                    <ColumnDefinition />
                                    <ColumnDefinition />
                                </Grid.ColumnDefinitions>''',
     '''                            <UniformGrid x:Name="QuickGrid" Columns="4">'''),
]


def main():
    src = io.open(P, encoding='utf-8').read()
    misses = []
    for old, new in PAIRS:
        if old not in src:
            misses.append(old.strip().splitlines()[0][:70])
            continue
        src = src.replace(old, new, 1)
    for old, new in []:
        if old not in src:
            misses.append('quickgrid')
            continue
        src = src.replace(old, new, 1)

    # 常用功能四张卡：去掉 Grid.Column，改成等分 + 统一边距
    for i in range(4):
        src = src.replace('                                <Border Grid.Column="%d" Style="{StaticResource CardStyle}" Height="82" Cursor="Hand"\n'
                          '                                        Padding="13"' % i,
                          '                                <Border Style="{StaticResource CardStyle}" Height="82" Cursor="Hand"\n'
                          '                                        Padding="13" Margin="0,0,11,0" MarginPlaceholder="%d"' % i)
    # 最后一列右边距清零
    src = src.replace('Margin="0,0,11,0" MarginPlaceholder="3"', 'Margin="0" MarginPlaceholder="3"')
    src = src.replace('\n                                    <ColumnDefinition />\n', '')
    src = src.replace('                            </Grid>\n', '                            </UniformGrid>\n', 1)
    io.open(P, 'w', encoding='utf-8', newline='\n').write(src)
    print('misses:', misses if misses else 'none')


if __name__ == '__main__':
    main()
