# Install script for directory: /mnt/c/Users/MANJU L/Downloads/ns-allinone-3.46.1/ns-3.46.1/contrib/defiance

# Set the install prefix
if(NOT DEFINED CMAKE_INSTALL_PREFIX)
  set(CMAKE_INSTALL_PREFIX "/usr/local")
endif()
string(REGEX REPLACE "/$" "" CMAKE_INSTALL_PREFIX "${CMAKE_INSTALL_PREFIX}")

# Set the install configuration name.
if(NOT DEFINED CMAKE_INSTALL_CONFIG_NAME)
  if(BUILD_TYPE)
    string(REGEX REPLACE "^[^A-Za-z0-9_]+" ""
           CMAKE_INSTALL_CONFIG_NAME "${BUILD_TYPE}")
  else()
    set(CMAKE_INSTALL_CONFIG_NAME "default")
  endif()
  message(STATUS "Install configuration: \"${CMAKE_INSTALL_CONFIG_NAME}\"")
endif()

# Set the component getting installed.
if(NOT CMAKE_INSTALL_COMPONENT)
  if(COMPONENT)
    message(STATUS "Install component: \"${COMPONENT}\"")
    set(CMAKE_INSTALL_COMPONENT "${COMPONENT}")
  else()
    set(CMAKE_INSTALL_COMPONENT)
  endif()
endif()

# Install shared libraries without execute permission?
if(NOT DEFINED CMAKE_INSTALL_SO_NO_EXE)
  set(CMAKE_INSTALL_SO_NO_EXE "1")
endif()

# Is this installation the result of a crosscompile?
if(NOT DEFINED CMAKE_CROSSCOMPILING)
  set(CMAKE_CROSSCOMPILING "FALSE")
endif()

# Set default install directory permissions.
if(NOT DEFINED CMAKE_OBJDUMP)
  set(CMAKE_OBJDUMP "/usr/bin/objdump")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.46.1-defiance-default.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.46.1-defiance-default.so")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.46.1-defiance-default.so"
         RPATH "/usr/local/lib:\$ORIGIN/:\$ORIGIN/../lib:/usr/local/lib64:\$ORIGIN/:\$ORIGIN/../lib64")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib" TYPE SHARED_LIBRARY FILES "/mnt/c/Users/MANJU L/Downloads/ns-allinone-3.46.1/ns-3.46.1/build/lib/libns3.46.1-defiance-default.so")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.46.1-defiance-default.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.46.1-defiance-default.so")
    file(RPATH_CHANGE
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.46.1-defiance-default.so"
         OLD_RPATH "/mnt/c/Users/MANJU L/Downloads/ns-allinone-3.46.1/ns-3.46.1/build/lib::::::::::::"
         NEW_RPATH "/usr/local/lib:\$ORIGIN/:\$ORIGIN/../lib:/usr/local/lib64:\$ORIGIN/:\$ORIGIN/../lib64")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/usr/bin/strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.46.1-defiance-default.so")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include/ns3" TYPE FILE FILES
    "/mnt/c/Users/MANJU L/Downloads/ns-allinone-3.46.1/ns-3.46.1/contrib/defiance/model/action-application.h"
    "/mnt/c/Users/MANJU L/Downloads/ns-allinone-3.46.1/ns-3.46.1/contrib/defiance/model/agent-application.h"
    "/mnt/c/Users/MANJU L/Downloads/ns-allinone-3.46.1/ns-3.46.1/contrib/defiance/model/aggregated-info.h"
    "/mnt/c/Users/MANJU L/Downloads/ns-allinone-3.46.1/ns-3.46.1/contrib/defiance/model/base-test.h"
    "/mnt/c/Users/MANJU L/Downloads/ns-allinone-3.46.1/ns-3.46.1/contrib/defiance/model/channel-interface.h"
    "/mnt/c/Users/MANJU L/Downloads/ns-allinone-3.46.1/ns-3.46.1/contrib/defiance/model/data-collector-application.h"
    "/mnt/c/Users/MANJU L/Downloads/ns-allinone-3.46.1/ns-3.46.1/contrib/defiance/model/history-container.h"
    "/mnt/c/Users/MANJU L/Downloads/ns-allinone-3.46.1/ns-3.46.1/contrib/defiance/model/observation-application.h"
    "/mnt/c/Users/MANJU L/Downloads/ns-allinone-3.46.1/ns-3.46.1/contrib/defiance/model/reward-application.h"
    "/mnt/c/Users/MANJU L/Downloads/ns-allinone-3.46.1/ns-3.46.1/contrib/defiance/model/rl-application-container.h"
    "/mnt/c/Users/MANJU L/Downloads/ns-allinone-3.46.1/ns-3.46.1/contrib/defiance/model/rl-application.h"
    "/mnt/c/Users/MANJU L/Downloads/ns-allinone-3.46.1/ns-3.46.1/contrib/defiance/model/simple-channel-interface.h"
    "/mnt/c/Users/MANJU L/Downloads/ns-allinone-3.46.1/ns-3.46.1/contrib/defiance/model/socket-channel-interface.h"
    "/mnt/c/Users/MANJU L/Downloads/ns-allinone-3.46.1/ns-3.46.1/contrib/defiance/helper/communication-helper.h"
    "/mnt/c/Users/MANJU L/Downloads/ns-allinone-3.46.1/ns-3.46.1/contrib/defiance/helper/rl-application-helper.h"
    "/mnt/c/Users/MANJU L/Downloads/ns-allinone-3.46.1/ns-3.46.1/build/include/ns3/defiance-module.h"
    )
endif()

