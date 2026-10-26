/*!
 * Drage
 * Version: 1.0.1
 * Author: Zaron Chen
 * License: MIT
 *
 * Copyright (c) 2023 Zaron Chen
 */

export const Drage = ({
	width = "300px",
	height = "25px",
	posX = "16px",
	posY = "16px",
	ver = "top",
	hor = "left",
	padding = "0px 10px 10px 10px",
	roundCorner = "6px",
	containerColor = "rgba(0, 0, 0, 0.5)",
	dragAreaColor = "rgba(0, 0, 0, 0)",
	//edgePadding = 16,
	//within = false,
} = {}) => {
	// get device type: "touch" | "mouse"
	let DEVICE_TYPE
	try {
		document.createEvent("TouchEvent")
		DEVICE_TYPE = "touch"
	} catch (e) {
		DEVICE_TYPE = "mouse"
	}

	let MOUSE_OVER = false
	let DRAGGING = false
	const onMouseOver = () => (MOUSE_OVER = true)
	const onMouseOut = () => (MOUSE_OVER = false)
	// allows users to check if the mouse is over the Drage
	const onDrage = () => MOUSE_OVER

	const html = document.documentElement
	const body = document.body

	// for drag calculate
	let offsetX, offsetY

	// create container, Drage
	const container = document.createElement("div")
	container.style.cssText = `
		background-color: ${containerColor};
		width: ${width};
		position: absolute;
		${ver}: 0;
		${hor}: 0;
		border-radius: ${roundCorner};
		z-index: 999;
	`
	document.querySelector("body").appendChild(container)

	// get element style property value
	const getStyleProperty = (element, property) =>
		getComputedStyle(element).getPropertyValue(property)

	// create drag area
	const topLeftRadius = getStyleProperty(container, "border-top-left-radius")
	const topRightRadius = getStyleProperty(container, "border-top-right-radius")
	const dragArea = document.createElement("div")
	dragArea.style.cssText = `
		background-color: ${dragAreaColor};
		height: ${height};
		cursor: grab;
		border-radius: ${topLeftRadius} ${topRightRadius} 0px 0px;
		user-select: none;
		touch-action: none;
	`
	container.appendChild(dragArea)

	// create content area
	const contentArea = document.createElement("div")
	contentArea.style.cssText = `
		margin: ${padding};
		user-select: none;
		touch-action: none;
	`
	container.appendChild(contentArea)

	// initial container position
	const initPosition = () => {
		const initX = hor === "left" ? posX : hor === "right" ? `-${posX}` : "0px"
		const initY = ver === "top" ? posY : ver === "bottom" ? `-${posY}` : "0px"
		container.style.transform = `translate(${initX}, ${initY})`
	}
	initPosition()

	// mousedown | touchstart
	const onDragStart = (e) => {
		DRAGGING = true
		const { clientX, clientY } = e.type === "mousedown" ? e : e.touches[0]
		offsetX = clientX - container.getBoundingClientRect()[hor]
		offsetY = clientY - container.getBoundingClientRect()[ver]
		dragArea.style.cursor = "grabbing"
		body.style.cursor = "grabbing"
		container.style.transition = "none"
	}

	// mousemove | touchmove
	const onDragMove = (e) => {
		if (!DRAGGING) return
		onMouseOver()
		const { clientX, clientY } = e.type === "mousemove" ? e : e.touches[0]
		const offsetXCorrection = hor === "right" ? html.offsetWidth : 0
		const offsetYCorrection = ver === "bottom" ? html.offsetHeight : 0
		let x = clientX - offsetX + window.scrollX - offsetXCorrection
		let y = clientY - offsetY + window.scrollY - offsetYCorrection
		//if (within) [x, y] = stayWithinScreen(x, y)
		container.style.transform = `translate(${x}px, ${y}px)`
	}

	// mouseup | mouseleave | touchend
	const onDragEnd = () => {
		if (!DRAGGING) return
		DRAGGING = false
		dragArea.style.cursor = "grab"
		body.style.cursor = ""
		container.style.transition = "transform 0.3s ease"
	}

	/* // let position stay within the screen
	const stayWithinScreen = (x, y) => {
		const screenWidth = window.innerWidth + window.scrollX
		const screenHeight = window.innerHeight + window.scrollY
		const maxWidth = screenWidth - container.offsetWidth - edgePadding
		const maxHeight = screenHeight - container.offsetHeight - edgePadding
		x = Math.min(Math.max(edgePadding, x), maxWidth)
		y = Math.min(Math.max(edgePadding, y), maxHeight)
		return [x, y]
	} */

	/* // resize
	const onResize = () => {
		let x = parseFloat(container.style.transform.split("(")[1])
		let y = parseFloat(container.style.transform.split(",")[1])
		;[x, y] = stayWithinScreen(x, y)
		container.style.transform = `translate(${x}px, ${y}px)`
		container.style.transition = "transform 0.12s ease"
	} */

	// dragArea event listeners
	dragArea.addEventListener("mousedown", onDragStart)
	dragArea.addEventListener("touchstart", onDragStart)

	// document event listeners
	document.addEventListener("mousemove", onDragMove)
	document.addEventListener("mouseup", onDragEnd)
	document.addEventListener("mouseleave", onDragEnd)
	document.addEventListener("touchmove", onDragMove)
	document.addEventListener("touchend", onDragEnd)

	// container event listeners
	container.addEventListener("mouseover", onMouseOver)
	container.addEventListener("mouseout", onMouseOut)
	container.addEventListener("touchstart", onMouseOver)
	container.addEventListener("touchend", () => {
		onMouseOut()
		onDragEnd()
	})
	container.addEventListener("click", () => {
		DEVICE_TYPE === "touch" && onMouseOut()
		onDragEnd()
	})

	//if (within) window.addEventListener("resize", onResize)

	return { onDrage, contentArea }
}
